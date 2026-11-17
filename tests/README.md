# Python 回归测试

当前测试集中在本目录，使用仓库内开发包 `minecraft_testkit` 运行。从仓库根目录执行：

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-test.txt
.venv/Scripts/python.exe -m minecraft_testkit verify
.venv/Scripts/python.exe -m minecraft_testkit test
.venv/Scripts/python.exe -m minecraft_testkit test --pattern test_native_log_stream.py
```

| 测试模块 | 范围 |
| --- | --- |
| `test_packaged_client` / `test_memory_build_classpath` | 发布身份、启动参数、历史构建输入 |
| `test_observe_packaged_client` / `test_neutral_reload_adapter` / `test_reload_before_recorder` | 观察、重载证据链与录制器契约 |
| `test_native_log_stream` / `test_native_diagnostic_review` / `test_native_model_trace` | 滚动日志与原生诊断归因 |
| `test_windows_process_identity` / `test_windows_snapshot_io` | Windows 原生身份和文件共享语义 |
| `test_client_experiment` / `test_source_experiment` / `test_performance_analysis` | 实验设计、重放、性能分析规则 |
| `test_ci` / `test_minecraft_testkit` | 发布守卫、脚本索引与样例完整性 |

共用合成夹具在 `minecraft_testkit/fixtures/`；真实历史样例及来源清单在
`minecraft_testkit/data/`。合成序列用于测试拒绝/接受边界，不能作为真实游戏操作记录。
关闭窗口用例的合成采样时钟独立于机器调度；后台线程仍通过真实事件启动、释放和
join，关闭后的完成事件不能延长已经冻结的路线采样窗口。
Windows 原生测试保留已有平台限制；测试可运行短命 Python 子进程及临时 Git 仓库，
不启动 Minecraft/JVM，也不发送游戏输入。

测试入口在独立 Python 子进程中设置旧式 `tools/` 模块的导入路径，并按完整的
`tests.*` 包名发现测试；不会修改调用者环境或当前运行客户端的源码。筛选结果为
零个测试时返回失败。旧的全量 `unittest discover -s tools -p 'test_*.py'` 由
`tools/test_suite.py` 的标准 `load_tests` 钩子转发到相同测试集合；旧文件名的精确
筛选应改用新入口。两种入口都不会扫描证据中的冻结 `test_*.py`。
本套件是仓库开发包，尚未作为独立 pip 分发包。

新增回归测试放在本目录；共用构造器放入 `fixtures/`，样例按清单登记来源和哈希。
Minecraft MCP 的后续边界见 [扩展计划](../docs/MINECRAFT_MCP.md)。
