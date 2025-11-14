# CVD监控程序性能优化项目

## 项目简介

本项目是一个高性能的CVD（Cumulative Volume Delta，累积成交量差）监控程序，通过多个版本的迭代优化，实现了显著的性能提升。

## 项目背景

CVD是一个重要的技术指标，用于分析市场买卖力量的对比。本项目通过WebSocket实时获取交易数据，计算并存储CVD指标，为量化交易提供数据支持。

## 版本说明

### V1 - 初始版本 (`get_cvd_optimized.py`)
- 基础功能实现
- 单文件写入模式

### V2 - 优化版 (`get_cvd_optimized_v2.py`)
- 性能优化
- 改进数据处理逻辑
- 详细性能分析

### V3 - 双模式版 (`get_cvd_optimized_v3.py`) ⭐推荐
- 支持单文件和多文件两种写入模式
- 灵活的配置选项
- 最佳性能表现

## 核心功能

1. **实时数据采集**：通过WebSocket连接交易所，实时获取交易数据
2. **CVD计算**：高效计算累积成交量差指标
3. **多种写入模式**：
   - 单文件模式：所有数据写入一个CSV文件
   - 多文件模式：按日期分割文件存储
4. **性能优化**：
   - 批量数据处理
   - 高效的I/O操作
   - 内存优化

## 配置文件

- `config.yaml`：主配置文件，包含交易所、交易对等基础配置
- `settings.yaml`：运行设置，包含写入模式、数据目录等配置
- `settings_single_file.yaml`：单文件模式配置示例
- `settings_multi_file.yaml`：多文件模式配置示例
- `settings_both_modes.yaml`：双模式配置示例

## 性能报告

项目包含多份详细的性能分析和优化报告：

- `CVD监控程序性能分析与优化建议报告.md`：初始性能分析
- `CVD监控程序优化对比报告.md`：版本间性能对比
- `CVD监控程序写入模式性能对比报告.md`：不同写入模式的性能对比
- `双模式同时写入性能测试报告.md`：双模式性能测试
- `performance_analysis_notes.md`：性能分析笔记

## 使用说明

详细的使用说明请参考：

- `CVD监控程序 - V3 双模式版使用说明.md`（推荐）
- `CVD监控程序 - 最终优化版使用说明.md`
- `CVD监控程序 - 优化版使用说明.md`

## 技术栈

- Python 3.x
- WebSocket (picows)
- Pandas
- YAML配置管理

## 快速开始

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置文件：
   - 复制 `config.yaml` 并根据需要修改
   - 选择合适的 `settings_*.yaml` 配置

3. 运行程序：
```bash
python get_cvd_optimized_v3.py
```

## 数据输出

程序会将CVD数据保存到 `cvd_data_optimized/` 目录下，根据配置的写入模式：
- 单文件模式：`cvd_data_all.csv`
- 多文件模式：`cvd_data_YYYYMMDD.csv`

## 日志

运行日志保存在 `log/` 目录下，便于问题排查和性能监控。

## 性能特点

- ✅ 高效的数据处理
- ✅ 灵活的存储模式
- ✅ 低内存占用
- ✅ 稳定的长时间运行
- ✅ 详细的性能监控

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License
