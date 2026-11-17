# CI/CD 与仓库维护

远端：[teamCreating/MTR-Memory-Saver](https://github.com/teamCreating/MTR-Memory-Saver)。
版本以 `gradle.properties` 为准，Java 和官方目标以 `config/targets.json` 为准。

## 每次提交

工作分支每次 commit 后自动 push 到 origin，首次使用 `git push --set-upstream origin <分支>`。
main 经 PR 合入；自动 push 更新工作分支。提交作者和 walkthrough 要求见根目录 AGENTS.md。

`build.yml` 在分支 push、指向 main 的 PR、merge group、手动运行或发布流程调用时执行：

- Linux、Windows Server 2022 分别运行 Python 工具测试。
- 从目标矩阵选出官方目标，在 Linux、Windows 分别构建、运行 Java 和独立观察器测试、校验发行包。
- Linux 生成官方目标 ZIP、构建身份清单和 ZIP SHA-256，作为14天保留的 Actions artifacts；各平台保留测试报告，包括失败报告。
- 固定名称 CI 汇总全部任务。任何失败、取消或跳过的必需任务都会使检查失败。

Windows runner 在 checkout 前启用其临时环境的 Git 长路径支持。实际原生进程身份读取仅在其已限定的平台运行；Windows Server CI 不继承 Windows 10 build19045 的运行资格，也不替代游戏验收。

完整工具测试安装 `requirements-test.txt` 的固定依赖，并使用仓库内两份已按 `config/legacy-baselines.json` 校验的原始0.3.0 JAR。它们是历史身份适配的测试输入，不属于当前发行产物。临时目录夹具先解析成真实路径，再生成日志头，避免 Windows 短路径别名破坏同实例校验。

## main 保护

版本化配置位于 `.github/main-ruleset.json`：

- 对 main 启用规则，管理员没有预设 bypass。
- 必须经 PR，所有讨论必须解决；当前不强制另一个人的批准，以适配单维护者流程。
- 必需检查 CI 来自 GitHub Actions，且基于最新 main。
- 禁止删除、非快进更新，保持线性历史；使用 squash 或 rebase 合入。

`.github/release-tags-ruleset.json` 禁止修改或删除 v* 标签。
这些 JSON 是可审查配置；服务端是否生效以 GitHub rulesets API 的实际回读为准。

## 发布

先将版本和代码通过 main 的 PR/CI，再创建与版本完全一致的标签，例如：

```powershell
git tag v0.4.8
git push origin v0.4.8
```

`release.yml` 检查标签等于 v + modVersion，且标签提交属于 main；随后重新执行完整 CI、验证全部官方 ZIP 与清单、校验包内 JAR 指纹。全部成功才创建 GitHub pre-release 并上传 ZIP 与校验和。既有 release 不自动覆盖。

手动运行 Release 是演练：只允许选择 main，执行相同构建和资产校验，不创建标签或 GitHub Release。因此可以测试 CD 而无需发布当前候选。

普通构建仅有 contents:read；仅最后的发布任务具有 contents:write。Actions 固定到完整提交 SHA，使用平台 GITHUB_TOKEN，无需长期发布密钥。自动发布是开发候选交付，不扩大 SUPPORT.md 中的运行支持声明。

初始化保留本地完整历史和远端初始提交。远端原始 MIT 声明另存为 `LICENSE.repository`；产品 LICENSE 原字节保持不变。

参考：[GitHub rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)、[GITHUB_TOKEN 权限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)。
