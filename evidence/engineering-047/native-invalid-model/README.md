# 官方 Invalid model 静态归因

证据时间：2026-11-15T07:41:37.719140+08:00（UTC+08:00）。范围仅官方 MTR 4.1.0-beta.2，未验证 v6。

已定位官方 JAR 的程序生成源：`CustomResourceLoader.reload()` 在读取任何 registry 前创建轨道 `id=default`、`name=Default`，其便捷构造传入空 `modelResource` 和空 `textureResource`，随后调用 `VehicleModel.getModelLoaderBase()`。工厂先格式化纹理，再对原始模型字段检查 `.bbmodel`/`.obj` 后缀；错误分支打印的是纹理标识。因此这条路径会打印 `[mtr:textures/block/transparent.png] Invalid model!`，日志本身不证明 PNG 损坏。

原始 archive SHA：`ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`。生成调用所在 entry：`org/mtr/client/CustomResourceLoader.class`，entry SHA：`ec7cfc6da67a42332c1cc3f89e0b5db5c0d7df4c657f3267ef82346b1dd28934`。该 ID 来自 class 字面量，无 registry entry 或 JSON pointer。

官方 JAR 加 16 包全部按准备计划和 catalogue 校验 SHA。两个 registry 共审计 4,200 个模型消费项，另按官方目录迁移规则审计 303 个旧格式项（289 对象、14 轨道），总计 4,503 项；没有不支持后缀的 authored 候选。每项保留 archive SHA、entry SHA、ID、JSON pointer 和原始模型/纹理字段。两个目录 JSON 来自 source 10 的 `assets/mtrsteamloco/eyecandies/mcav2.json` 与 source 15 的 `assets/mtrsteamloco/rails/guotie.json`。七个 sign-only legacy 声明单独记录，不混入模型消费计数。

功能边界：最终 style 精确为 `default` 时，官方二维绘制绕过该轨道模型；启用默认 3D 且为 TRAIN 时，精确 `default` 会映射至 `default_3d` 或 `default_3d_siding`。但是 `default_1/default_2` 可通过剥离方向后缀 lookup `default` 并进入模型渲染，是否实际可选或存在于世界尚未验证。声音路径仅读取 `soundIndex`。空模型 fallback 仍可能提交解析 worker；`shouldPreload=false` 不代表零开销。

这是静态来源与分支证据。未启动客户端、安装观察器、重载资源、修改实例或操作 UI；没有追踪具体日志行的运行时调用栈，也没有完成无 companion 基线。不得将其改写为 PNG 损坏、唯一运行时来源、无害噪音或游戏验收通过。

主要文件：`assessment.json`（来源、原生调用链和 registry 审计）、`legacy-directory-assessment.json`（目录消费者）、`rail-consumption-assessment.json`（功能边界）、相应 `*.javap.txt` 和模型消费明细。`sha256.json` 绑定本目录全部最终文件，排除自身。
