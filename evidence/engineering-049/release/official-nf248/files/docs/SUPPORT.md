# MTR Memory Saver support and artifact identity

This is a development candidate for **official-nf248**, version **0.4.7**.

Required: Minecraft **1.21.1**, Java **21**, NeoForge
**21.1.248 exactly**, and MTR **4.1.0-beta.2**.

MTR SHA-256: `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`.
Companion SHA-256: `e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99`.

The companion validates the loaded MTR binary before applying its Mixins. Install
only one matching memory companion. The original MTR and authored resource packs
need no modification. See [installation and rollback](INSTALL.md), the
[configured target matrix](../config/targets.json), and [license](../LICENSE).

## Evidence included for this exact artifact

Recorded packaged checks: 24 lifecycle and 18 actual-resource checks; normal exit, settled workspace and readable JFR. A separate same-version wrong-binary client was rejected before registration.

Exact packaged 0.4.7 official base-resource fault lifecycle and same-version binary rejection. No full-pack gameplay, full ResourceManager reload, endurance or performance acceptance.

The [version-bound evidence summary](VALIDATION.json) records its source identity
and scope. Detailed raw receipts remain in the source repository. Build identity
and packaged fault checks do not establish complete gameplay, resource-reload
endurance, route duration or controlled performance. Historical heap/scheduler
settings apply to their recorded fixtures; this bundle adds no JVM scheduler
override and makes no new memory or speed guarantee.
