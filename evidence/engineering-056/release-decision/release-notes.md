0.4.8 is a client-side development pre-release for Minecraft 1.21.1, Java 21,
**NeoForge 21.1.265 exactly**, and official MTR 4.1.0-beta.2.

Blockbench, OBJ and material inputs now stream through owned UTF-16 snapshots,
avoiding the full input String allocation that caused the earlier reload OOM.
The content digest is computed during snapshot writing, removing a disk read pass.

Validation of the packaged NF265 JAR includes 106 Java regressions, 69 actual
packaged lifecycle/resource/OBJ checks, fatal rejection of an incorrect MTR
binary, and twenty consecutive full sixteen-pack native reloads at a 3 GiB
heap. Independent final stability, normal exit and the final JFR reader also pass.
The release workflow repeats Linux/Windows CI and verifies the bundle's JAR hash.

The focused snapshot benchmark reduced median CPU time by 19.24% across six
pairs. This measures one input path. Whole-client performance benefits remain
unconfirmed: earlier practical Spark measurements missed the performance targets,
and concurrent host workloads limit conclusions from wall-clock timings.
This pre-release does not certify every vehicle interaction or a two-hour route.

Install the JAR inside the ZIP in the client `mods` folder. Remove earlier
MTR Memory Saver companion JARs first; keep the exact supported MTR and loader.
The independent test observer is excluded from the release bundle.

Tested product JAR SHA-256:
`920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b`.

- [Packaged checks](https://github.com/teamCreating/MTR-Memory-Saver/tree/main/evidence/engineering-056/nf265-packaged)
- [Twenty-reload proof](https://github.com/teamCreating/MTR-Memory-Saver/tree/main/evidence/engineering-056/nf265-reload20)
- [Snapshot optimization and benchmark](https://github.com/teamCreating/MTR-Memory-Saver/tree/main/evidence/engineering-055/snapshot-digest)
- [Support scope](https://github.com/teamCreating/MTR-Memory-Saver/blob/main/docs/SUPPORT.md)
