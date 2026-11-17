# 历史脚本索引与样例数据

`historical-scripts.json` 索引 Git 跟踪的 `evidence/**/*.py`，逐文件记录原路径、
工程批次、字节数和 SHA-256。目录包含一次性驱动、审计程序及冻结源码；统一标为
`reference-only`，清单本身不授予任何脚本执行资格。原件保留在证据树，避免破坏
封存路径、源码指纹和旧报告引用。新增历史 Python 文件后，用下面的命令产生候选
清单，审查后更新文件并记录 walkthrough：

```powershell
python -m minecraft_testkit inventory > .cache/historical-scripts.next.json
python -m minecraft_testkit list
python -m minecraft_testkit verify
```

`samples.json` 列出真正用于测试的两组最小样例，每个成员记录原始 `source`、
字节数和 SHA-256。`samples/` 是逐字节副本，原件没有修改。`verify` 同时比较副本
和原始证据；测试读取目录前先校验清单，新增或缺少成员也会失败。

| 数据集 | 用途与边界 |
| --- | --- |
| `native-log-rollover` | 原始 gzip 和较早 startup prefix，测试无损解压及跨日日志拼接；不构成新的启动或重载通过 |
| `neutral-reload-contract` | 历史 observer 1.0.2 的状态、目标、进程、计划、启动、日志、epoch 和诊断契约；生成的多次重载是测试控制，不能算实际游戏重载 |

样例里的绝对路径、PID、版本和时间都是历史数据，不得用于寻找或接管当前客户端。
测试只向临时目录复制/修改样例。完整证据的 proof 依赖仍在原证据树；这些小数据集
不是可独立重放全部验收的封存包。既有0.3.0测试JAR继续按
`config/legacy-baselines.json` 从 `dist/` 验证，避免再复制二进制。

合成数据构造器在 `../fixtures/`，与原始历史样例分开。后续 MCP 的数据资源可以复用
`samples.sample_directory()` 和这些来源记录，但必须保留其历史/合成性质。
