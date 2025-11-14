# -*- coding: utf-8 -*-

"""
优化版 CVD 监控程序
主要优化点:
1. 使用单一 asyncio 事件循环,所有 WebSocket 连接作为协程并发运行
2. 移除全局锁,使用 asyncio 的线程安全特性
3. 所有交易对数据写入同一个 CSV 文件,批量写入
4. 共享 aiohttp.ClientSession,复用连接池
"""

import asyncio
import time
import os
import yaml
import signal
import sys
import ssl
import logging
import logging.handlers
import csv
from datetime import datetime
from collections import defaultdict
import aiohttp
import cysimdjson
from typing import Dict, List, Optional

# --- 配置加载 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.yaml")
SYMBOLS_CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
DATA_DIR = os.path.join(SCRIPT_DIR, "cvd_data_optimized")
LOG_DIR = os.path.join(SCRIPT_DIR, "log")

# --- 日志设置 ---
def setup_logging(log_dir=LOG_DIR):
    """配置日志到文件和控制台"""
    os.makedirs(log_dir, exist_ok=True)
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
            print(f"创建日志目录 {log_dir} 时出错: {e}")
            return None

    # 文件处理器
    log_file = os.path.join(log_dir, 'cvd_monitor_optimized.log')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    logger.info("日志配置完成。")
    return logger

# 初始化日志
logger = setup_logging()

# 默认值
proxy_settings = {'host': '127.0.0.1', 'port': 7890, 'type': 'http'}
symbols_to_monitor = []
save_interval_minutes = 15
cvd_max_age_days = 6
config_check_interval_seconds = 600

# 加载通用设置
try:
    with open(SETTINGS_FILE, 'r') as f:
        settings = yaml.safe_load(f)
        proxy_settings = settings.get('proxy', proxy_settings)
        save_interval_minutes = settings.get('data_saving', {}).get('interval_minutes', save_interval_minutes)
        cvd_max_age_days = settings.get('cvd_reset', {}).get('max_age_days', cvd_max_age_days)
        config_check_interval_seconds = settings.get('config_reload', {}).get('check_interval_seconds', config_check_interval_seconds)
except FileNotFoundError:
    logger.warning(f"警告: 未找到设置文件 {SETTINGS_FILE}。使用默认设置。")
except yaml.YAMLError as e:
    logger.error(f"解析设置文件 {SETTINGS_FILE} 时出错: {e}。使用默认设置。")
except Exception as e:
    logger.error(f"加载设置时发生意外错误: {e}。使用默认设置。")

# --- 符号格式解析 ---
def parse_new_symbol_format(symbols_data):