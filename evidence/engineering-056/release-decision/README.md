# 0.4.8 scoped development release decision

2026-11-23, UTC+08:00. The user authorized continued verification and publication,
and limited new testing to NeoForge 21.1.265. The selected release target is
`official-nf265`; historical presets remain available for explicit source builds.

Eligible for the repository's existing GitHub **pre-release** workflow after the
protected-main PR and required CI pass. This decision does not mark full runtime
or performance acceptance as complete. The exact product JAR SHA-256 is
`920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b`.

- 106 Java regressions, small-heap streaming controls and 354 Python tool tests pass.
- The exact packaged client passes 24 lifecycle, 18 strict-resource and 27 OBJ
  checks. A separate wrong-MTR-binary client exits fatally before registration.
  Both JFR recordings pass the actual JDK reader. See [packaged binding](../nf265-packaged/README.md).
- The exact optimized candidate passes twenty consecutive real full-sixteen-pack
  reloads, independent intermediate/final stable checks, normal JVM exit and a
  closed nineteen-file installed-hash audit. See [literal replay proof](../nf265-reload20/README.md).
- Snapshot hashing now happens during writing, removing a complete disk read
  pass. Six balanced real-input benchmark pairs show a 19.24% median CPU-time
  reduction in that path. See [optimization evidence](../../engineering-055/snapshot-digest/README.md).

Whole-client memory/loading targets have not been established for this optimized
candidate. Earlier practical Spark trials missed their budgets, and concurrent
host workloads make wall-clock attribution inconclusive. The paired sensitivity
analysis retains those outcomes; no anomalous timing was silently deleted or
converted to a pass. Exhaustive gameplay interactions and a two-hour route also
remain pending. Release notes and support documentation retain these limits.

The pre-release is therefore for testing the verified streaming/lifecycle changes,
without a general performance-benefit claim. CI/CD verifies exact target/version,
protected-main tag ancestry, ZIP checksums and the tested JAR hash before upload.
The neutral observer and acceptance fixture are excluded from the product bundle.
