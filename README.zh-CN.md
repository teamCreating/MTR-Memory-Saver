<img src="src/main/resources/pack.png" width="72" align="right" alt="MTR Memory Saver">

# MTR Memory Saver

[English](README.md) | **简体中文**

Minecraft `1.21.1`（客户端）· NeoForge `21.1.265` · Java `21` · 官方 MTR `4.1.0-beta.2` · Mod ID：`mtr_memory_sharing` · [MIT 协议](LICENSE)

**MTR Memory Saver** 是面向 **Minecraft Transit Railway（官方 MTR `4.1.0-beta.2`）** 的客户端内存与资源加载优化模组。它通过在车辆注册与热重载阶段消除重复模型/JSON 解析、流式处理大文本、有界压缩存储 CPU 侧顶点与资源文本，显著压低运行所需的 Java 堆上限并避免连续重载 OOM，同时完整保留原生 MTR 的模型解析、坐标变换、AABB 包围盒、展示部位与车门/地板逻辑。

---

## 核心实测进展（官方 MTR `4.1.0-beta.2`）

在 16 个高负载测试资源包下，原生官方 MTR `4.1.0-beta.2` 存在大量 CPU 侧 `StoredVertexData` 对象常驻、非展示矩阵元数据滞留、车辆 JSON 重复解析、`RESOURCE_CACHE` 无界增长以及整块 `String` 分配峰值问题。截至 **`0.4.8`**（`official-nf265`），主要定量变化如下：

| 指标维度 | 基线 / 优化前状态 | 当前状态 / 优化后实测 | 夹具口径与边界说明 |
| :--- | :--- | :--- | :--- |
| **最低稳定启动 Java 堆上限** | `8 GiB`（`v0.1.1`）；`v0.2.9` 在 `3 GiB` 启动 OOM | **`3 GiB`（`-Xmx3072M`，堆上限降低 `62.5%`）**（`v0.3.0` / `0.4.x`） | 实测两代官方 `4.1.0-beta.2` 16 包夹具；Windows 工作集 / 私有提交仍约 `4.46–5.36 GiB` |
| **CPU `StoredVertexData` 数量** | `79,359,867` 个活跃实例（`v0.1.1`） | **`0` 个**（`v0.2.0+` 36 B/顶点 `Deflater.BEST_SPEED` 分块压缩） | 旧 16 包堆直方图；391 上海模型（`47.37M` 顶点）压缩载荷 `367.77 MB` |
| **非展示部位矩阵变换元数据** | `2,494,194` 个实例（约 `753 MiB`） | **`2,234` 个（−99.91%）**（仅留 `PartType.DISPLAY`） | `v0.2.1` 5 GiB 堆直方图：整体浅堆 `3.04 -> 2.31 GiB`（−24.17%） |
| **车辆配置 Gson 浅堆** | `385,752,224` B（`385.75 MB`） | **`99,865,272` B（`99.87 MB`，−74.11%）** | `v0.2.2` 5 GiB 堆直方图：整体浅堆 `−579 MiB`（−24.50%） |
| **资源文本缓存驻留** | `2,000,187,675` 码元 / `592,010,155` B 压缩 | **`96 MiB`（`100,663,296` B）有界 LRU**（`v0.3.0+`） | 旧 16 包每周期驱逐 `3,010` 次；超限条目旁路处理 |
| **大文本 SHA-256 哈希分配** | `16M` 码元：`134.22 MB` / `536.87 MB` / `738.20 MB` | **`136.7–136.9 KB`（降低 `99.898%–99.981%`）** | `v0.2.9+` 固定 4K/8K 数组流式编码（ASCII / 混合 / Unicode） |
| **单遍摘要优化（`0.4.8`）** | 初版写盘后重读一遍通道算 SHA-256 | **NF265 线程 CPU −19.24% / 耗时 −19.37%** | [engineering-055](evidence/engineering-055/snapshot-digest/README.md) 65.26 MB 真实 BBModel 6 对微基准（6/6 改善；单输入路径） |
| **`3 GiB` 连续全 16 包 `F3+T` 重载** | `0.4.7` 第 4 次 OOM；`0.4.8` 初版第 7 次 OOM | **`20 / 20` 次连续通过（0 OOM）** | [engineering-056](evidence/engineering-056/nf265-reload20/README.md) 原生目录 16 包（`1,092` 声明 / `1,091` ID），正常退出码 `0`，JFR 可读 |
| **异常强杀残留与错包拦截** | `0.4.6` 强杀留 `.utf16`；`0.4.4` 错包继续进主菜单 | **`4 / 4` 次强杀零残留 + 注册前退出码 `1` 中止** | `DELETE_ON_CLOSE` 单通道内核回收（`0.4.7+`）；`MixinInitialisationError`（`0.4.5+`） |

> 验证范围提示：`0.4.8` 已通过 `3 GiB` 堆下全包启动与连续 `20/20` 次重载耐久，但整客户端受控性能对比仍处于待完成状态——详见下方「[当前验证边界](#当前验证边界)」。

---

## 支持目标与安装方法

**`0.4.8`** 开发预发布仅面向 **`official-nf265`** 构建并发布（依赖指纹与版本约束由 [config/targets.json](config/targets.json) 唯一定义）：

| 配置项 | 精确要求 |
| :--- | :--- |
| 构建预设 | `official-nf265` |
| Minecraft / Java | `1.21.1`（仅客户端）· Java `21` |
| NeoForge 版本 | `21.1.265`（精确版本） |
| 官方 MTR `4.1.0-beta.2` SHA-256 | `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa` |
| 已测试产物 JAR (`0.4.8`) SHA-256 | `920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b` |

### 安装与回退

1. 前往 [GitHub Releases](https://github.com/teamCreating/MTR-Memory-Saver/releases/tag/v0.4.8) 下载 **`mtr-memory-saver-official-nf265-0.4.8.zip`**（完整更新日志见 [0.4.8 发布说明](docs/releases/v0.4.8.md)）。
2. 解压出内部的 **`mtr-memory-saver-official-nf265-0.4.8.jar`**，连同精确版本 NeoForge `21.1.265` 与官方 MTR `4.1.0-beta.2` 一并放入客户端 `mods/` 目录。
3. 安装前删除旧版 `mtr-memory-saver` / `mtr_memory_sharing` JAR（切勿混装多个版本）。模组启动时会校验磁盘上 MTR JAR 的全文件 SHA-256，不匹配则在车辆注册前抛出 `MixinInitialisationError` 并以退出码 `1` 中止。
4. 资源包保持放在 `resourcepacks/` 目录且无需修改。回退时关闭游戏并移除或替换为先前的匹配版本 JAR 即可。

完整安装说明与支持范围见 [docs/INSTALL.md](docs/INSTALL.md) 与 [docs/SUPPORT.md](docs/SUPPORT.md)。仓库另在 `config/targets.json` 保留历史定制 `Performance v6` 预设（`v6-nf248` / `v6-nf265`），目前新验证暂停。

---

## 核心架构概览

面向官方 MTR `4.1.0-beta.2` 的 `0.4.8` 采用四层架构与 18 项 Mixin/Accessor（详细设计与源码级分析见 [docs/TECHNICAL_PRINCIPLES.md](docs/TECHNICAL_PRINCIPLES.md) 与 [docs/RUNTIME_DESIGN.md](docs/RUNTIME_DESIGN.md)）：

1. **二进制身份校验（`CompatibilityPlugin` / `BinaryFingerprint`）**：在 Mixin `onLoad` 阶段流式计算实际 MTR JAR 的 SHA-256，不匹配即抛出 `MixinInitialisationError` 终止启动。
2. **两级单飞缓存与有界并发调度（`GenerationWorkCache`）**：先按 L1 路径键 `(providerIdentity, modelId, textureId, flipV)` 命中并返回既有 Future，跳过 I/O、解码与哈希；工作池采用公平 `2 + 64` 信号量队列与轻量描述符；L2 内容别名先关闭快照与读许可再订阅，防止持有许可等待引发死锁；`StreamedObjCache` 按路径键隔离 `.mtl` 材质；`beginReload()` 在单锁内原子退役旧世代。
3. **流式快照、单遍摘要与 `96 MiB` LRU**：仅在 5 处已审计的官方 `ResourceProvider` 传入点包装快照句柄（`ResourceTextReadMixin`），通过单个 `CREATE_NEW | READ | WRITE | DELETE_ON_CLOSE` UTF-16 通道流式读取 `.bbmodel` / `.obj` / `.mtl`，并在写盘同一遍 `FilterReader` 循环完成 UTF-8 SHA-256 计算；传统接口经公平份额 `TextWorkspace` 避免死锁溢写，`BoundedTextCache` 以 `Deflater.BEST_SPEED` 将保留文本限制在 `96 MiB`。
4. **无损 36B 压缩网格、展示剪枝与 JSON 共享**：以 36 字节定长分块压缩存储顶点原生浮点位并还原 AABB（`PackedVertices` / `PackedModelGroupStore`），仅保留 `PartType.DISPLAY` 原始变换（`DisplayRetention`），同世代共享相同车辆配置 `JsonObject`（`VehicleJsonCache`）。

---

## 当前验证边界

### 已验证通过（`0.4.8` `official-nf265`，JAR `920c1f83...`）

- **离线自动化测试**：106 项 Java 回归测试（含 `-Xmx64M` 流式 vs `String.join` OOM 负对照）、682 份历史研究脚本校验与 354 项 Python 工具测试全部通过。
- **打包实机与门禁检查**：实机 NF265 客户端通过 24 生命周期 + 18 严格资源 + 27 OBJ 共 **69 项检查**、全 16 包启动（`1,092` 声明 / `1,091` 去重 ID）、JFR 可读性检查，以及同版本假 MTR JAR 启动前退出码 `1` 拒绝（[engineering-056/nf265-packaged](evidence/engineering-056/nf265-packaged/README.md)）。
- **20 次连续全 16 包热重载（`3 GiB`）**：在独立 `-Xms512M -Xmx3072M` G1 JVM 中连续完成 **epochs 3–22 共 `20 / 20` 次真实 `F3+T` 重载**，包含 19 个中间双时钟 `>= 60 s` 稳定区间、末轮后 14/14 样本覆盖 `65.003 s`、`Alt+F4` 正常退出码 `0`、可读 `213,901,766` 字节 JFR，并经只读离线脚本 `verify_sealed.py` 全项复现（[engineering-056/nf265-reload20](evidence/engineering-056/nf265-reload20/README.md)）。

### 尚未认证 / 待关闭门禁

- **整客户端性能验收未完成**：先前的 NF248 12-JVM 实用 Spark 对照（[engineering-054](evidence/engineering-054/practical-spark/README.md)）未通过预设门槛（稳态私有内存 `−0.282%` 未达 `<= -10%`，加载耗时 `+9.840%` 超出 `+5%`），叠加并发宿主机负载使耗时因果归因判为 `inconclusive`；优化单遍摘要后的 `920c1f83...` 尚未在 [client-experiment.json](config/client-experiment.json) 下完成 48-JVM 整客户端对照。
- **待关闭实机项（P1）**：独立显示帧呈现时间采集（普通权限 ETW 拒访、PresentMon 未输出有效 CSV）、两小时不间断路线稳定（历史尝试 01–03 失败）及全车系外观/车窗/车门/上下车交互。

---

## 构建与校验

需准备 **Java 21 JDK**（`JAVA_HOME`）。构建与回归测试不依赖已启动的游戏实例或标记文件（详见 [BUILDING.md](BUILDING.md) 与 [tests/README.md](tests/README.md)）：

```powershell
# 构建默认 official-nf265 JAR 与 .build.json 构建身份清单
./gradlew.bat build -Ptarget=official-nf265

# 运行无头 Java 单元测试与回归测试（official-nf265 共 106 项）
./gradlew.bat test

# 在 build/releases/ 生成可分发安装包 ZIP
./gradlew.bat releaseBundle

# 运行 Python 工具检验与回归测试（需安装 requirements-test.txt）
python -X utf8 -m minecraft_testkit verify
python -X utf8 -m minecraft_testkit test

# 只读离线复放已封存的 0.4.8 NF265 20 次重载证据
python -X utf8 evidence/engineering-056/nf265-reload20/verify_sealed.py
```

### 目录结构

- `src/main/java/` — 公共 Mixin、两级有界调度、UTF-16 快照、文本工作区/LRU、压缩网格、JSON/展示共享
- `src/targets/official/java/` — 官方 MTR `4.1.0-beta.2` 专属目标实现（`StreamedObjCache`、`ResourceTextReadMixin`、`VertexColorMixin` 等）
- `src/targets/v6/java/` — 历史定制 `Performance v6` ABI 适配代码（目前暂停）
- `config/` — 权威构建矩阵（`targets.json`）与冻结试验配置
- `evidence/` 与 `performance/` — 哈希索引封存的成功与失败实机记录及 `verify_sealed.py` 离线校验脚本
- `tools/` 与 `tests/` — 实机验收工具、JFR/Spark 导出器及 354 项 Python 回归测试

---

## 文档导航与协议

| 文档 | 内容说明 |
| :--- | :--- |
| [docs/TECHNICAL_PRINCIPLES.md](docs/TECHNICAL_PRINCIPLES.md) | 中文完整技术原理、架构图解、对照试验方法论与 `v0.1.1`–`0.4.8` 全阶段实测结果 |
| [docs/releases/v0.4.8.md](docs/releases/v0.4.8.md) | `v0.4.8` 中英双语发布说明 |
| [docs/RUNTIME_DESIGN.md](docs/RUNTIME_DESIGN.md) | 运行时并发不变量与行为契约（`0.4.7+`） |
| [docs/SUPPORT.md](docs/SUPPORT.md) · [docs/INSTALL.md](docs/INSTALL.md) | 精确依赖支持矩阵、安装与回退指南 |
| [BUILDING.md](BUILDING.md) · [docs/CI_CD.md](docs/CI_CD.md) | 可复现构建、受保护 `main` 规则与发布工作流 |
| [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md) · [docs/CLIENT_EXPERIMENT.md](docs/CLIENT_EXPERIMENT.md) · [docs/ENGINEERING_REVIEW.md](docs/ENGINEERING_REVIEW.md) | 受控配对试验方法与关键工程审视 |
| [docs/HISTORY.md](docs/HISTORY.md) · [TECHNICAL.md](TECHNICAL.md) | `0.1.x`–`0.3.x` 研究记录与早期英文技术归档 |
| [LICENSE](LICENSE) · [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | MIT 许可证（`Copyright (c) 2026 A-BenLi06`）与第三方声明 |
