# CVD监控程序 - 最终优化版使用说明

## 版本信息

**版本**: V2 (最终优化版)
**文件名**: `get_cvd_optimized_v2.py`
**更新日期**: 2025年11月14日

## 核心特性

本版本是CVD监控程序的最终优化版,集成了所有性能改进和功能增强:

- ✅ **单一asyncio事件循环架构** - 线程数从120+降至1个
- ✅ **完全消除锁竞争** - 利用asyncio单线程特性
- ✅ **可配置的写入模式** - 支持单文件/多文件两种模式
- ✅ **批量高效写入** - 两种模式均采用批量写入优化
- ✅ **智能CVD恢复** - 自动从历史数据加载CVD值
- ✅ **共享连接池** - 复用aiohttp连接,降低开销

## 配置说明

### 1. 交易对配置 (config.yaml)

```yaml
symbols:
  spot:
    - BTC/USDT
    - ETH/USDT
  futures:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
  coin-futures:
    - BTC/USD:BTC
```

### 2. 运行参数配置 (settings.yaml)

```yaml
proxy:
  host: "127.0.0.1"  # 代理地址,留空表示不使用代理
  port: 7890
  type: "http"

data_saving:
  interval_minutes: 1  # 数据保存间隔(分钟)
  use_single_file: false  # true=单文件模式, false=多文件模式

cvd_reset:
  max_age_days: 1  # CVD数据最大保留天数

config_reload:
  check_interval_seconds: 60  # 配置检查间隔(秒)
```

### 3. 写入模式选择

**重要配置项**: `data_saving.use_single_file`

#### 多文件模式 (推荐, `use_single_file: false`)

- **数据文件**: 每个交易对独立的CSV文件
  - 例如: `BTCUSDT_spot.csv`, `ETHUSDT_usdt-m.csv`
- **CSV格式**: `timestamp,price,cvd,period_volume`
- **优点**:
  - ⚡ 程序重启时快速加载历史CVD(恒定速度,不受数据规模影响)
  - 🛡️ 数据隔离,单个文件损坏不影响其他交易对
  - 📊 便于单独分析特定交易对
- **缺点**:
  - 📁 生成多个文件(120+),文件管理稍复杂
  - ⏱️ 写入耗时略长(~2-3ms vs ~1ms)

#### 单文件模式 (`use_single_file: true`)

- **数据文件**: 统一的CSV文件 `cvd_data_all.csv`
- **CSV格式**: `timestamp,symbol,price,cvd,period_volume`
- **优点**:
  - ⚡ 写入速度最快(~1ms)
  - 📁 只有一个数据文件,管理简单
  - 📊 便于跨交易对聚合分析
- **缺点**:
  - ⏳ 程序重启时加载历史CVD较慢(随数据增长而变慢)
  - ⚠️ 单文件损坏风险

**性能测试结论**: 

经过120个交易对的实际测试,两种模式的写入耗时都在毫秒级,对程序整体性能影响极小。**强烈推荐使用多文件模式**,因为其在长期运行场景下的快速重启能力是决定性优势。

## 使用方法

### 启动程序

```bash
# 前台运行
python3 get_cvd_optimized_v2.py

# 后台运行
nohup python3 get_cvd_optimized_v2.py > cvd.log 2>&1 &

# 查看日志
tail -f log/cvd_monitor_optimized.log
```

### 停止程序

```bash
# 方法1: 如果在前台运行,按 Ctrl+C

# 方法2: 如果在后台运行,找到进程ID并发送信号
ps aux | grep get_cvd_optimized_v2.py
kill -TERM <PID>
```

### 数据文件位置

- **多文件模式**: `cvd_data_optimized/SYMBOL_TYPE.csv`
- **单文件模式**: `cvd_data_optimized/cvd_data_all.csv`
- **日志文件**: `log/cvd_monitor_optimized.log`

## 性能表现

基于120个交易对的实际测试:

| 性能指标 | 数值 |
|---------|------|
| 线程数 | 1 (主线程) |
| 内存占用 | 极低 |
| CPU占用 | 极低 |
| 数据保存耗时(单文件) | ~1ms |
| 数据保存耗时(多文件) | ~2-3ms |
| 并发WebSocket连接 | 120+ |
| 平均处理速度 | 200+ 笔交易/秒 |

## CVD数据持久化机制

程序启动时会自动加载历史CVD值:

1. **多文件模式**: 读取每个交易对对应CSV文件的最后一行
2. **单文件模式**: 扫描统一CSV文件,找到每个交易对的最后一条记录
3. **时效性检查**: 如果文件修改时间超过`max_age_days`,则从0开始计算
4. **无缝累积**: CVD值持续累积,不会重置,确保数据连续性

## 依赖安装

```bash
sudo pip3 install aiohttp cysimdjson pyyaml
```

## 故障排查

### WebSocket连接失败

- 检查网络连接
- 如需代理,在`settings.yaml`中正确配置
- 查看日志获取详细错误信息

### 数据未保存

- 检查`cvd_data_optimized`目录权限
- 确认程序运行时间超过保存间隔
- 查看日志中的错误信息

### 程序重启后CVD值不对

- 检查CSV文件是否存在且格式正确
- 查看日志中的"加载CVD"相关信息
- 确认文件修改时间未超过`max_age_days`

## 最佳实践

1. **生产环境推荐配置**:
   - `use_single_file: false` (多文件模式)
   - `interval_minutes: 1` (每分钟保存一次)
   - `max_age_days: 1` (保留1天历史)

2. **定期备份**: 定期备份`cvd_data_optimized`目录

3. **日志监控**: 监控日志文件,及时发现异常

4. **资源监控**: 虽然程序资源占用极低,但仍建议监控系统资源

## 技术支持

如有问题,请查看:
- 日志文件: `log/cvd_monitor_optimized.log`
- 性能对比报告: `performance_comparison_report.md`
- 优化分析报告: `optimization_comparison.md`
