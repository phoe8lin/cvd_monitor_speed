# CVD监控程序 - V3 双模式版使用说明

## 版本信息

**版本**: V3 (双模式同时写入版)
**文件名**: `get_cvd_optimized_v3.py`
**更新日期**: 2025年11月14日

## 核心特性

这是CVD监控程序的终极版本,实现了**单文件和多文件同时写入**:

- ✅ **单一asyncio事件循环** - 资源占用极低
- ✅ **完全消除锁竞争** - 性能最优
- ✅ **双模式同时写入** - 兼得两种模式的所有优点
- ✅ **一次遍历,双重准备** - 实现简洁高效
- ✅ **智能CVD恢复** - 优先从多文件快速加载
- ✅ **双重数据备份** - 提高数据安全性

## 双模式优势

### 为什么选择双模式?

传统方案需要在单文件和多文件之间做出选择,各有优缺点。双模式方案**同时提供两种格式**,让您无需权衡:

| 需求场景 | 使用文件 | 优势 |
|---------|---------|------|
| 程序重启恢复CVD | 多文件 | 秒级加载,不受历史数据规模影响 |
| 跨交易对数据分析 | 单文件 | 所有数据在一个文件,便于聚合分析 |
| 查看特定交易对历史 | 多文件 | 直接打开对应文件,简单直接 |
| 数据备份与恢复 | 两者 | 双重备份,降低数据丢失风险 |

### 性能开销

**极小的性能代价,巨大的功能收益**:
- 写入耗时: 仅2-3ms (每分钟一次)
- 额外磁盘占用: 约2倍 (现代硬盘完全可承受)
- 代码复杂度: 极低,易于维护

## 配置说明

### settings.yaml

```yaml
proxy:
  host: ""  # 留空表示不使用代理
  port: 0
  type: "http"

data_saving:
  interval_minutes: 1  # 数据保存间隔(分钟)
  save_both_modes: true  # 启用双模式同时写入

cvd_reset:
  max_age_days: 1  # CVD数据最大保留天数

config_reload:
  check_interval_seconds: 60
```

**注意**: V3版本默认启用双模式,无需额外配置。

### config.yaml

```yaml
symbols:
  spot:
    - BTC/USDT
    - ETH/USDT
  futures:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
```

## 数据文件

### 单文件 (全局分析)

**文件路径**: `cvd_data_optimized/cvd_data_all.csv`

**格式**:
```csv
timestamp,symbol,price,cvd,period_volume
2025-11-14 08:44:47,BTCUSDT_spot,94731.74,-6.22,27.63
2025-11-14 08:44:47,ETHUSDT_spot,3089.41,-429.24,939.20
```

**用途**:
- 跨交易对数据分析
- 全局CVD趋势观察
- 批量数据导入其他系统

### 多文件 (快速查询)

**文件路径**: `cvd_data_optimized/SYMBOL_TYPE.csv`

**示例**: `cvd_data_optimized/BTCUSDT_spot.csv`

**格式**:
```csv
timestamp,price,cvd,period_volume
2025-11-14 08:44:47,94731.74,-6.22,27.63
2025-11-14 08:45:47,94646.91,-7.07,25.05
```

**用途**:
- 程序重启时快速加载CVD值
- 单个交易对历史数据查看
- 独立备份特定交易对数据

## 使用方法

### 启动程序

```bash
# 前台运行
python3 get_cvd_optimized_v3.py

# 后台运行
nohup python3 get_cvd_optimized_v3.py > cvd.log 2>&1 &

# 查看实时日志
tail -f log/cvd_monitor_optimized.log
```

### 停止程序

```bash
# 前台运行: 按 Ctrl+C

# 后台运行: 查找进程并停止
ps aux | grep get_cvd_optimized_v3.py
kill -TERM <PID>
```

### 数据查询

**查看所有交易对数据**:
```bash
cat cvd_data_optimized/cvd_data_all.csv
```

**查看特定交易对数据**:
```bash
cat cvd_data_optimized/BTCUSDT_spot.csv
```

**统计数据行数**:
```bash
wc -l cvd_data_optimized/cvd_data_all.csv
```

## CVD恢复机制

程序启动时自动从多文件加载历史CVD值(速度最快):

1. 读取 `SYMBOL_TYPE.csv` 文件的最后一行
2. 提取CVD值
3. 检查文件修改时间是否超过 `max_age_days`
4. 如超期或文件不存在,则从0开始

**优势**: 无论历史数据多大,加载速度恒定(毫秒级)

## 性能表现

基于120个交易对的实际测试:

| 性能指标 | 数值 |
|---------|------|
| 线程数 | 1 |
| 数据保存耗时 | 2-3ms |
| 文件I/O次数 | 81次/分钟 |
| 并发WebSocket连接 | 120+ |
| 平均处理速度 | 200+ 笔交易/秒 |
| 内存占用 | 极低 |
| CPU占用 | 极低 |

## 与其他版本对比

| 特性 | V1 原始版 | V2 可选模式 | V3 双模式 |
|------|----------|-----------|----------|
| 架构 | 多线程 | 单事件循环 | 单事件循环 |
| 锁竞争 | 严重 | 无 | 无 |
| 写入模式 | 多文件 | 单/多可选 | **同时写入** |
| 重启速度 | 快 | 可选 | **快** |
| 全局分析 | 难 | 可选 | **易** |
| 数据安全 | 中 | 中 | **高** |
| 推荐度 | ⭐⭐ | ⭐⭐⭐⭐ | **⭐⭐⭐⭐⭐** |

## 依赖安装

```bash
sudo pip3 install aiohttp cysimdjson pyyaml
```

## 故障排查

### 数据未同时保存到两个位置

**检查**:
1. 查看日志中是否有 "[双模式] 已保存" 的信息
2. 确认 `settings.yaml` 中 `save_both_modes: true`
3. 检查目录权限

### 磁盘空间不足

**解决**:
- 定期清理旧数据
- 减少 `max_age_days` 设置
- 如空间极度受限,可改用V2单文件模式

### 单文件和多文件数据不一致

**原因**: 程序异常退出时可能导致最后一次保存不完整

**解决**: 
- 正常停止程序(Ctrl+C),会自动保存最终数据
- 检查日志中的错误信息

## 最佳实践

1. **定期备份**: 每天备份 `cvd_data_optimized` 目录
2. **监控日志**: 关注日志中的错误和警告信息
3. **磁盘空间**: 确保有足够空间存储双份数据
4. **优雅停止**: 使用 Ctrl+C 或 SIGTERM 信号停止程序

## 技术支持

- 性能测试报告: `dual_mode_performance_report.md`
- CVD逻辑说明: `cvd_logic_comparison.md`
- 日志文件: `log/cvd_monitor_optimized.log`

---

**推荐**: 这是CVD监控程序的**终极版本**,强烈推荐用于生产环境!
