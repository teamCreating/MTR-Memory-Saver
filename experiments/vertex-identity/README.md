# Immutable vertex reuse experiment

These v0.1.2 sources are excluded from the default companion build. The archived JAR is `../../archive/mtr-memory-sharing-neoforge-v012.jar`; its build manifest records the source fingerprints before archival.

`tools/VertexIdentityAudit.java` compares `VertexSharing.unchanged` with the unmodified target release's actual `StoredVertexData.modify`. Use the archived candidate JAR, official NeoForge MTR beta.2 JAR and patched test-client libraries on the classpath. It passed 1,002,880 raw-bit comparisons, including independent positions, normals and offsets, mirrored transforms and signed-zero/NaN/subnormal cases.

Ordinary all-pack startup and F3+T reload passed at 8 GiB, but 6 GiB failed. Both v0.1.1 and v0.1.2 post-acceptance histograms counted exactly 79,359,867 vertex records. This experiment therefore did not reduce the observed parsed full-pack vertex population. Default delivery and builds retain v0.1.1. See [recorded results](../../evidence/neoforge-v012-acceptance.json).
