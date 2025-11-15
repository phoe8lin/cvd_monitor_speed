#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
优化版 CVD 监控程序 V3 - 双模式同时写入

主要特性:
1. 使用单一 asyncio 事件循环,所有 WebSocket 连接作为协程并发运行
2. 移除全局锁,使用 asyncio 的线程安全特性
3. 支持单文件和多文件同时写入(可配置)
4. 共享 aiohttp.ClientSession,复用连接池
5. 高效批量写入,最小化I/O开销

核心指标说明:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
指标             | 计算方式                    | 清零时机              | 清零频率
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cvd              | 主动买入量-主动卖出量累积   | 程序启动时(条件性)    | 文件超过6天
period_volume    | 所有交易量累加              | 每次保存数据后        | 默认1分钟
trade_count      | 交易笔数计数                | 永不清零              | 仅程序重启
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CVD清零条件(程序启动时检查):
- CSV文件不存在
- CSV文件为空
- CSV文件太旧(超过 cvd_max_age_days,默认6天)
- CSV文件解析失败

配置参数:
- cvd_reset.max_age_days: CVD文件最大保留天数(默认6天)
- data_saving.interval_minutes: 数据保存间隔(默认1分钟,影响period_volume清零频率)
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
save_interval_minutes = 1
cvd_max_age_days = 6
config_check_interval_seconds = 600
save_both_modes = True  # 默认同时写入两种模式

# 加载通用设置
try:
    with open(SETTINGS_FILE, 'r') as f:
        settings = yaml.safe_load(f)
        proxy_settings = settings.get('proxy', proxy_settings)
        save_interval_minutes = settings.get('data_saving', {}).get('interval_minutes', save_interval_minutes)
        cvd_max_age_days = settings.get('cvd_reset', {}).get('max_age_days', cvd_max_age_days)
        config_check_interval_seconds = settings.get('config_reload', {}).get('check_interval_seconds', config_check_interval_seconds)
        save_both_modes = settings.get('data_saving', {}).get('save_both_modes', save_both_modes)
except FileNotFoundError:
    logger.warning(f"警告: 未找到设置文件 {SETTINGS_FILE}。使用默认设置。")
except yaml.YAMLError as e:
    logger.error(f"解析设置文件 {SETTINGS_FILE} 时出错: {e}。使用默认设置。")
except Exception as e:
    logger.error(f"加载设置时发生意外错误: {e}。使用默认设置。")

# --- 符号格式解析 ---
def parse_new_symbol_format(symbols_data):
    """解析配置文件中的符号格式"""
    parsed_symbols = []
    if not isinstance(symbols_data, dict):
        logger.warning("警告: 配置文件中的 'symbols' 数据格式无效。预期为字典。")
        return []

    spot_symbols = symbols_data.get('spot', [])
    if isinstance(spot_symbols, list):
        for symbol_str in spot_symbols:
            if isinstance(symbol_str, str) and '/' in symbol_str:
                symbol_base = symbol_str.replace('/', '').upper()
                parsed_symbols.append({'symbol': symbol_base, 'type': 'spot'})
            else:
                logger.warning(f"警告: 跳过无效的现货符号格式: {symbol_str}")

    futures_symbols = symbols_data.get('futures', [])
    if isinstance(futures_symbols, list):
        for symbol_str in futures_symbols:
            if isinstance(symbol_str, str) and '/' in symbol_str:
                clean_symbol = symbol_str.split(':')[0].replace('/', '').upper()
                parsed_symbols.append({'symbol': clean_symbol, 'type': 'usdt-m'})
            else:
                logger.warning(f"警告: 跳过无效的期货符号格式: {symbol_str}")

    coin_futures_symbols = symbols_data.get('coin-futures', [])
    if isinstance(coin_futures_symbols, list):
        for symbol_str in coin_futures_symbols:
            if isinstance(symbol_str, str) and '/' in symbol_str:
                clean_symbol = symbol_str.split(':')[0].replace('/', '').upper()
                parsed_symbols.append({'symbol': clean_symbol, 'type': 'coin-m'})
            else:
                logger.warning(f"警告: 跳过无效的币本位期货符号格式: {symbol_str}")

    return parsed_symbols

try:
    with open(SYMBOLS_CONFIG_FILE, 'r') as f:
        symbols_config = yaml.safe_load(f)
        symbols_to_monitor = parse_new_symbol_format(symbols_config.get('symbols', {}))

        if not symbols_to_monitor:
            logger.warning(f"警告: 在 {SYMBOLS_CONFIG_FILE} 中未找到有效的符号配置。不会监控任何符号。")
except FileNotFoundError:
    logger.warning(f"警告: 未找到符号配置文件 {SYMBOLS_CONFIG_FILE}。不会监控任何符号。")
except yaml.YAMLError as e:
    logger.error(f"解析符号配置文件 {SYMBOLS_CONFIG_FILE} 时出错: {e}。不会监控任何符号。")
    symbols_to_monitor = []
except Exception as e:
    logger.error(f"加载符号配置时发生意外错误: {e}。不会监控任何符号。")
    symbols_to_monitor = []

# --- 从CSV加载最后的CVD值 ---
def load_last_cvd_from_separate_csv(csv_file_path, max_age_days=1):
    """
    从独立的CSV文件加载最后的CVD值
    
    CVD清零逻辑说明:
    程序启动时,CVD会在以下情况下从0开始计算:
    1. CSV文件不存在
    2. CSV文件为空(大小为0或只有表头)
    3. CSV文件太旧(文件修改时间超过 max_age_days 天,默认6天)
    4. CSV文件解析失败(格式错误或数据损坏)
    
    如果以上条件都不满足,则从CSV文件的最后一行加载CVD值,继续累积计算
    
    参数:
        csv_file_path: CSV文件路径
        max_age_days: CVD数据最大保留天数(默认1天,实际使用时为6天)
    
    返回:
        float: 最后的CVD值,如果需要重置则返回0.0
    
    CSV格式: timestamp,price,cvd,period_volume,trade_count
    """
    if not os.path.exists(csv_file_path):
        return 0.0

    try:
        file_size = os.path.getsize(csv_file_path)
        file_mtime = os.path.getmtime(csv_file_path)
        file_mtime_dt = datetime.fromtimestamp(file_mtime)
        now = datetime.now()

        if (now - file_mtime_dt).days > max_age_days:
            logger.info(f"CSV文件 {csv_file_path} 太旧（{(now - file_mtime_dt).days} 天）。将从0开始CVD计算。")
            return 0.0

        if file_size == 0:
            return 0.0

        if file_size < 100:
            with open(csv_file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                row_count = sum(1 for _ in reader)
                if row_count <= 1:
                    return 0.0

        # 读取文件末尾
        last_line = ""
        chunk_size = min(file_size, 4096)
        
        with open(csv_file_path, 'rb') as f:
            f.seek(-chunk_size, 2)
            last_chunk = f.read().decode('utf-8', errors='ignore')
            lines = last_chunk.splitlines()
            if lines:
                last_line = lines[-1]

        if last_line:
            try:
                parts = last_line.split(',')
                if len(parts) >= 3:
                    last_cvd = float(parts[2])
                    logger.info(f"从独立CSV文件 {csv_file_path} 加载了最后的CVD值: {last_cvd}")
                    return last_cvd
            except (ValueError, IndexError) as e:
                logger.warning(f"解析CSV文件 {csv_file_path} 的最后一行时出错: {e}。将从0开始CVD计算。")

        return 0.0
    except Exception as e:
        logger.error(f"从CSV文件 {csv_file_path} 加载CVD时发生错误: {e}。将从0开始CVD计算。")
        return 0.0

# --- CVD监控器类 (优化版) ---
class SymbolCvdMonitor:
    """使用 asyncio 实现的 CVD 监控器类"""
    
    def __init__(self, symbol_config, shared_session, data_store, data_dir):
        """初始化 CVD 监控器"""
        self.symbol_raw = symbol_config['symbol']
        self.type = symbol_config['type']
        self.shared_session = shared_session
        self.data_store = data_store
        self.data_dir = data_dir
        
        self.symbol_lower = self.symbol_raw.lower()
        self.stream_name = f"{self.symbol_lower}@aggTrade"
        self.shared_key = f"{self.symbol_raw}_{self.type}"
        
        # 从多文件模式加载初始CVD (优先使用多文件,因为加载更快)
        csv_file_path = os.path.join(data_dir, f"{self.shared_key}.csv")
        initial_cvd = load_last_cvd_from_separate_csv(csv_file_path, cvd_max_age_days)
        
        self.cvd = initial_cvd
        self.period_volume = 0.0
        self.last_price = None
        self.websocket_url = self._get_websocket_url()
        
        # 创建 JSON 解析器
        self.json_parser = cysimdjson.JSONParser()
        
        # 运行状态
        self.running = True
        self.ws = None
        
        # 重连相关
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 20
        self.max_reconnect_delay = 60
        self.initial_reconnect_delay = 5
        
        # 统计信息
        self.trade_count = 0
        self.last_log_time = time.time()
        
        # 初始化数据存储
        self.data_store[self.shared_key] = {
            'cvd': self.cvd,
            'last_price': self.last_price,
            'period_volume': self.period_volume,
            'trade_count': self.trade_count
        }
    
    def _get_websocket_url(self):
        """获取 WebSocket URL"""
        base_url = ""
        if self.type == 'spot':
            base_url = "wss://stream.binance.com:9443/ws/"
        elif self.type == 'usdt-m':
            base_url = "wss://fstream.binance.com/ws/"
        elif self.type == 'coin-m':
            base_url = "wss://dstream.binance.com/ws/"
        else:
            raise ValueError(f"不支持的市场类型: {self.type} for symbol {self.symbol_raw}")
        
        return f"{base_url}{self.stream_name}"
    
    def calculate_cvd(self, trade_data):
        """
        计算 CVD (Cumulative Volume Delta) 和周期成交量
        
        核心指标说明:
        1. CVD (累积成交量差):
           - 计算方式: 主动买入量 - 主动卖出量的累积
           - 清零时机: 程序启动时(如果CSV文件不存在/太旧/损坏)
           - 运行期间: 持续累积,不清零
           
        2. period_volume (周期交易量):
           - 计算方式: 所有交易量的累加(不区分买卖方向)
           - 清零时机: 每次保存数据后自动清零
           - 清零频率: 默认1分钟(可在settings.yaml配置)
           
        3. trade_count (交易笔数):
           - 计算方式: 简单计数
           - 清零时机: 永不清零,仅程序重启时归零
           - 用途: 统计和日志输出
        
        注意: 在单线程asyncio环境下,无需锁保护
        """
        try:
            quantity = float(trade_data.at_pointer("/q"))
            is_buyer_maker = trade_data.at_pointer("/m")
            price = float(trade_data.at_pointer("/p"))
            
            delta = quantity if not is_buyer_maker else -quantity
            
            self.cvd += delta
            self.period_volume += quantity
            self.last_price = price
            
            # 直接更新共享数据(无需锁)
            self.data_store[self.shared_key]['cvd'] = self.cvd
            self.data_store[self.shared_key]['last_price'] = self.last_price
            self.data_store[self.shared_key]['period_volume'] = self.period_volume
            self.data_store[self.shared_key]['trade_count'] = self.trade_count
            
            self.trade_count += 1
            current_time = time.time()
            
            if current_time - self.last_log_time >= 60:
                logger.info(f"[{self.shared_key}] 统计: 已处理 {self.trade_count} 笔交易 | CVD: {self.cvd:.4f} | 价格: {price:.4f}")
                self.last_log_time = current_time
            
        except Exception as e:
            logger.error(f"[{self.shared_key}] 处理交易数据时出错: {e}")
    
    async def process_message(self, message_bytes):
        """处理收到的 WebSocket 消息"""
        try:
            data = self.json_parser.parse(message_bytes)
            
            try:
                event_type = data.at_pointer("/e")
                if event_type == "aggTrade":
                    self.calculate_cvd(data)
                    return
            except Exception:
                pass
                
            try:
                stream = data.at_pointer("/stream")
                event_type = data.at_pointer("/data/e")
                if stream == self.stream_name and event_type == "aggTrade":
                    self.calculate_cvd(data.at_pointer("/data"))
                    return
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"[{self.shared_key}] 处理消息时出错: {e}")
    
    async def connect_and_monitor(self):
        """连接到 WebSocket 并持续监控"""
        logger.info(f"[{self.shared_key}] 启动监控...")
        
        while self.running:
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                logger.error(f"[{self.shared_key}] 超过最大重连次数。停止监控。")
                break
            
            if self.reconnect_attempts > 0:
                delay = min(self.initial_reconnect_delay * (2 ** self.reconnect_attempts), self.max_reconnect_delay)
                logger.info(f"[{self.shared_key}] 尝试重连 #{self.reconnect_attempts + 1}，等待 {delay:.2f} 秒...")
                await asyncio.sleep(delay)
            
            if not self.running:
                break
            
            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                async with self.shared_session.ws_connect(
                    self.websocket_url,
                    ssl=ssl_context,
                    heartbeat=30
                ) as ws:
                    self.ws = ws
                    logger.info(f"[{self.shared_key}] WebSocket 连接成功")
                    self.reconnect_attempts = 0
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            message_bytes = msg.data.encode('utf-8')
                            await self.process_message(message_bytes)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await self.process_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"[{self.shared_key}] WebSocket错误: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.warning(f"[{self.shared_key}] WebSocket已关闭")
                            break
                
            except Exception as e:
                logger.error(f"[{self.shared_key}] WebSocket 连接错误: {e}")
            finally:
                self.ws = None
                if self.running:
                    self.reconnect_attempts += 1
        
        logger.info(f"[{self.shared_key}] 监控器已停止")
    
    def stop(self):
        """停止监控器"""
        logger.info(f"[{self.shared_key}] 停止监控器...")
        self.running = False
    
    def reset_period_volume(self):
        """
        重置周期交易量
        
        说明:
        - 此方法在每次保存数据后自动调用
        - 仅清零 period_volume,不影响 cvd 和 trade_count
        - 调用频率: 默认1分钟(由 save_interval_minutes 配置)
        """
        self.period_volume = 0.0
        self.data_store[self.shared_key]['period_volume'] = 0.0

# --- 数据保存功能 (双模式同时写入) ---
async def save_cvd_data_both_modes(data_store, monitors, data_dir):
    """
    同时以单文件和多文件两种模式保存CVD数据
    优化策略: 一次遍历数据,同时准备两种格式的写入
    """
    os.makedirs(data_dir, exist_ok=True)
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 统一CSV文件路径
    unified_csv = os.path.join(data_dir, "cvd_data_all.csv")
    
    # 收集数据 (一次遍历)
    unified_rows = []  # 单文件模式的行
    separate_files = {}  # 多文件模式的数据 {文件路径: 行数据}
    saved_count = 0
    
    for key, monitor in monitors.items():
        if key not in data_store:
            continue
        
        data = data_store[key]
        cvd = data.get('cvd', 0.0)
        last_price = data.get('last_price', 0.0)
        period_volume = data.get('period_volume', 0.0)
        trade_count = data.get('trade_count', 0)

        if (last_price is None or last_price == 0) and cvd == 0:
            continue

        if last_price is None:
            last_price = 0.0

        # 准备单文件数据
        unified_rows.append([timestamp, key, last_price, cvd, period_volume, trade_count])

        # 准备多文件数据
        csv_file = os.path.join(data_dir, f"{key}.csv")
        separate_files[csv_file] = [timestamp, last_price, cvd, period_volume, trade_count]
        
        saved_count += 1
    
    # 写入单文件 (一次性批量写入)
    if unified_rows:
        file_exists = os.path.exists(unified_csv)
        with open(unified_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['timestamp', 'symbol', 'price', 'cvd', 'period_volume', 'trade_count'])
            writer.writerows(unified_rows)
    
    # 写入多文件 (批量处理)
    for csv_file, row_data in separate_files.items():
        try:
            file_exists = os.path.exists(csv_file)
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'price', 'cvd', 'period_volume', 'trade_count'])
                writer.writerow(row_data)
        except Exception as e:
            logger.error(f"保存文件 {csv_file} 时出错: {e}")
    
    # 重置周期交易量
    for monitor in monitors.values():
        monitor.reset_period_volume()
    
    logger.info(f"[双模式] 已保存 {saved_count} 个符号的CVD数据 (单文件+多文件)")

async def data_saver_task(data_store, monitors, data_dir, interval_seconds, shutdown_event):
    """数据保存协程任务 (双模式)"""
    logger.info(f"启动数据保存任务(双模式同时写入)，间隔: {interval_seconds} 秒")
    
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(interval_seconds)
            
            if not shutdown_event.is_set():
                logger.info("开始保存数据...")
                start_time = time.time()
                
                await save_cvd_data_both_modes(data_store, monitors, data_dir)
                
                elapsed = time.time() - start_time
                logger.info(f"数据保存完成，耗时: {elapsed:.3f} 秒")
        except asyncio.CancelledError:
            logger.info("数据保存任务被取消")
            break
        except Exception as e:
            logger.error(f"数据保存任务中发生错误: {e}", exc_info=True)
            await asyncio.sleep(60)
    
    logger.info("数据保存任务正在退出...")

# --- 主程序 ---
async def main():
    """主异步函数"""
    logger.info(f"初始化 CVD 监视器 (双模式同时写入)...")
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if not symbols_to_monitor:
        logger.warning("警告: 没有符号要监控。请检查配置文件。")
        return
    
    # 共享数据存储
    data_store = {}
    
    # 创建共享的 aiohttp.ClientSession
    proxy_url = None
    if proxy_settings.get('host') and proxy_settings.get('port'):
        proxy_url = f"{proxy_settings.get('type', 'http')}://{proxy_settings['host']}:{proxy_settings['port']}"
        logger.info(f"使用代理: {proxy_url}")
    
    session = aiohttp.ClientSession()
    
    # 创建所有监控器
    monitors = {}
    tasks = []
    
    for config in symbols_to_monitor:
        try:
            symbol_raw = config['symbol']
            symbol_type = config['type']
            shared_key = f"{symbol_raw}_{symbol_type}"
            
            logger.info(f"创建监控器: {shared_key}")
            monitor = SymbolCvdMonitor(
                symbol_config=config,
                shared_session=session,
                data_store=data_store,
                data_dir=DATA_DIR
            )
            
            monitors[shared_key] = monitor
            task = asyncio.create_task(monitor.connect_and_monitor())
            tasks.append(task)
            
        except Exception as e:
            logger.error(f"创建监控器时出错: {e}", exc_info=True)
    
    logger.info(f"\n--- 已创建 {len(monitors)} 个监控器 (双模式同时写入) ---")
    
    # 创建关闭事件
    shutdown_event = asyncio.Event()
    
    # 创建数据保存任务
    save_interval_seconds = save_interval_minutes * 60
    if save_interval_seconds <= 0:
        save_interval_seconds = 900
    
    saver_task = asyncio.create_task(
        data_saver_task(data_store, monitors, DATA_DIR, save_interval_seconds, shutdown_event)
    )
    tasks.append(saver_task)
    
    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info("\n用户中断。正在关闭...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("正在监控 CVD。按 Ctrl+C 停止。")
    
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("\n接收到键盘中断...")
        shutdown_event.set()
    finally:
        logger.info("正在停止所有监控器...")
        
        for monitor in monitors.values():
            monitor.stop()
        
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 最后保存一次数据
        try:
            logger.info("保存最终数据...")
            start_time = time.time()
            
            await save_cvd_data_both_modes(data_store, monitors, DATA_DIR)
            
            elapsed = time.time() - start_time
            logger.info(f"最终数据保存完成，耗时: {elapsed:.3f} 秒")
        except Exception as e:
            logger.error(f"保存最终数据时出错: {e}")
        
        await session.close()
        
        logger.info("所有任务已停止。程序退出。")

if __name__ == "__main__":
    if logger is None:
        print("初始化日志失败。退出。")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被中断")
    finally:
        logging.shutdown()
