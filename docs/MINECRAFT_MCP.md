# Minecraft MCP 后续扩展计划

状态：**规划阶段，尚未实现 MCP server、传输层或客户端控制接口**。
本次先将历史调试经验整理成仓库开发测试包 `minecraft_testkit`，集中当前回归测试、
合成构造器、带来源的样例及历史脚本索引。Memory Saver 仍是独立 Minecraft mod；
测试包可作为将来抽取通用 Minecraft MCP 的基础。

## 现有边界

| 层 | 当前实现 | 后续工作 |
| --- | --- | --- |
| 证据与样例 | `minecraft_testkit.samples`、`catalog`、`records` | 包装为带来源、哈希和范围说明的数据资源 |
| 测试控制 | `minecraft_testkit/fixtures/` 和 `tests/` | 给未来适配器复用成功、缺失、过期、错进程、未完成和取消场景 |
| 实例与观察 | `tools/packaged_client.py`、`observe_packaged_client.py`、Windows helpers | 抽取显式实例/会话接口，保留真实 PID/创建时间/完整命令行与原生句柄绑定 |
| 日志与诊断 | `native_log_stream.py`、`native_diagnostic_review.py`、分析器 | 提供结构化只读结果和原始证据引用，保持完整性与错误归因 |
| 录制与实验 | `reload_before_recorder.py`、`client_experiment.py` | 独立任务句柄、状态查询、正常停止与结果读取；保留原始终态和未完成原因 |
| 版本适配 | `config/targets.json`、consumer/review 契约 | 将通用 Minecraft 生命周期和 MTR 专属字段分离；动态报告已验证能力 |

当前工具有同目录导入和源码指纹依赖，测试入口仅在测试子进程中适配导入路径。
将来抽取库时应显式注入实例、目标矩阵、策略和输出目录，并保留原CLI兼容性；
不能直接把任意历史脚本或任意 shell 命令暴露为 MCP tool。

## 建议实施顺序

1. 先把已校验的样例、历史清单和离线分析结果映射为只读资源。资源采用显式ID，
   通过清单解析成员；返回历史/合成标记、来源、哈希和结论范围。
2. 抽取不启动游戏的纯分析能力，定义输入/输出 schema、错误和版本契约，再用
   本测试包验证。协议适配层与分析逻辑分开，避免传输细节进入mod。
3. 再接入明确选定实例的观察会话。超时不代表任务已结束；应先查询已有句柄的
   实际状态，防止重复启动、重复输入或覆盖原始输出。
4. 最后实现实际启动、输入、资源重载和停止操作。每次操作绑定实例和会话；保留
   发起/确认收据，并通过真实游戏事件验证完成。API返回成功或合成epoch不能代替
   实际重载完成。交互权限遵守调用方已提供的授权，不新增反复确认流程。

以上资源/工具分层是本项目的设计建议，依据 MCP 对
[Resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) 和
[Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) 的定义。
接入时应重新核对当时的协议/SDK版本；本次不添加SDK依赖、监听端口或后台服务。

## 扩展验收

未来适配器至少保留：无客户端离线测试、路径/来源校验、实例身份不匹配拒绝、
旧数据不能提升为新会话结果、取消与故障保留真实终态、Windows平台资格检查，
以及真实隔离客户端的独立验证。CI通过仍不能授予20次重载、路线、性能或正常退出
通过，也不扩大当前官方MTR支持范围；v6新验证继续暂停。

运行方式见 [tests/README.md](../tests/README.md)，脚本入口见
[tools/README.md](../tools/README.md)，样例范围见
[data/README.md](../minecraft_testkit/data/README.md)。
