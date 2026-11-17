# Python 工具与历史脚本入口

可维护的命令行工具继续保留在此目录，路径也是现有启动计划和 source pins 的组成部分。
Python 回归测试已从 `tools/test_*.py` 移到 [tests/](../tests/README.md)。
`test_suite.py` 仅保留旧全量 unittest discovery 的标准兼容入口，测试本体不重复存放。

| 职责 | 当前入口 |
| --- | --- |
| 打包、目标矩阵与历史构建 | `build_vehicle_memory_mod.py`、`ci.py`、`legacy_identity.py`、`legacy/` |
| 隔离客户端计划、启动与诊断捕获 | `packaged_client.py`、`capture_diagnostic_client.py` |
| 观察、重载前证据、日志和 Windows 原生适配 | `observe_packaged_client.py`、`reload_before_recorder.py`、`native_log_stream.py`、`windows_process_identity.py`、`windows_snapshot_io.py` |
| 实验与分析 | `client_experiment.py`、`client_experiment_analysis.py`、`benchmark_sources.py`、`source_experiment_analysis.py`、`analyze_performance_jfr.py`、`analyze_native_model_trace.py`、`native_diagnostic_review.py` |
| 构建回归、图标和原生审计 | `verify_admission_regression.py`、`verify_namespace_relocation.py`、`render_pack_icon.py`、[acceptance/](acceptance/README.md) |

历史一次性采集脚本、审计脚本和冻结源码位于 `evidence/`，按
[历史脚本清单](../minecraft_testkit/data/historical-scripts.json) 检索；不搬动其原始文件。
运行 `python -m minecraft_testkit list` 查看分组，`verify` 校验字节和样例来源。
清单只读取文件，绝不导入或批量执行历史脚本。重放某个历史结果时，仍应使用该结果
自己的封存说明和版本绑定依赖。

测试和共用样例见 [测试包说明](../tests/README.md)；后续抽取通用 Minecraft 能力并
接入 MCP 的计划见 [Minecraft MCP](../docs/MINECRAFT_MCP.md)。
