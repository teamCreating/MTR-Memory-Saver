# {{modName}} support and artifact identity

This is a development candidate for **{{target}}**, version **{{version}}**.

Required: Minecraft **{{minecraft}}**, Java **{{java}}**, NeoForge
**{{neoForge}} exactly**, and MTR **{{mtrVersion}}**.

MTR SHA-256: `{{mtrSha256}}`.
Companion SHA-256: `{{artifactSha256}}`.

The companion validates the loaded MTR binary before applying its Mixins. Install
only one matching memory companion. The original MTR and authored resource packs
need no modification. See [installation and rollback](INSTALL.md), the
[configured target matrix](../config/targets.json), and [license](../LICENSE).

## Evidence included for this exact artifact

{{runtimeSummary}}

The [version-bound evidence summary](VALIDATION.json) records its source identity
and scope. Detailed raw receipts remain in the source repository. Build identity
and packaged fault checks do not establish complete gameplay, resource-reload
endurance, route duration or controlled performance. Historical heap/scheduler
settings apply to their recorded fixtures; this bundle adds no JVM scheduler
override and makes no new memory or speed guarantee.
