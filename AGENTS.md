# Memory Saver 项目协作约定

开始任务时读取 [agent.md](agent.md)。这是独立 Git 仓库；在父工作区中位于 `vehicle-memory`，提交和 push 均在本仓库内执行。

- 平台为 Windows 10 22H2 专业工作站版，使用 PowerShell 7。
- 每次修改完成后，运行相关检查，并将改动内容、思路和验证结果写入根目录 `walkthrough.md`，时间戳须包含 UTC 偏移。
- 每次修改形成提交；作者使用 `A-BenLi06 <ben_li06@outlook.com>`，不要使用 Codex 身份。
- **每次 commit 成功后立即自动 push 当前工作分支到 origin，无需再次询问。** 首次使用 `git push --set-upstream origin <当前分支>`，后续使用 `git push`。用户明确要求仅本地操作或禁止推送时，以用户的新指令为准。
- 远端为 `https://github.com/teamCreating/MTR-Memory-Saver.git`。提交前核对仓库和分支；若在 main 上开始新工作，先创建 `codex/<任务名>` 分支。main 经 PR 和必需的 CI 检查合入，不直接推送、不绕过保护。
- push 失败时保留本地提交，读取远端状态并处理正常同步问题；不得 force-push、删除远端分支或重写他人的提交来掩盖失败。最终回复如实说明 push 是否成功。
- 不轻易硬编码语言、字段或目标；优先读取已有配置和发布版本的真实契约。
- 不将项目协作要求写进产品界面；使用正确逻辑，不用 hack 掩盖问题。
- 新验证继续针对官方 MTR 4.1.0-beta.2；v6 验证保持暂停。CI 构建与单元测试不能替代游戏中的重载、路线、交互和性能验收。
- 用户自 2026-11-23 起将后续本机验证目标限定为 NeoForge 21.1.265，无需继续执行 21.1.248 测试。已有 248 记录保留原范围。

CI/CD 和分支规则见 [docs/CI_CD.md](docs/CI_CD.md)。
