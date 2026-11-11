# Preserved delivery artifacts

All 29 existing JARs were moved without changing their bytes. JARs are local,
ignored outputs; their original build manifests and this index are tracked.
Fresh checkouts can rebuild using [BUILDING.md](../BUILDING.md). New builds
default to ignored `dist/local/`; they do not overwrite these deliveries.

`releases/` holds the previous top-level deliveries; `compatibility/` holds
loader/release-specific builds; `experiments/` and `archive/` retain historical
candidates. Use the [main guide](../README.md) to choose a tested version.

| Artifact | Mod version | Loader | Build manifest |
| --- | --- | --- | --- |
| [archive/mtr-memory-sharing-neoforge-v011.jar](archive/mtr-memory-sharing-neoforge-v011.jar) | 0.1.1 | neoforge 21.1.265 | [JSON](archive/mtr-memory-sharing-neoforge-v011.build.json) |
| [archive/mtr-memory-sharing-neoforge-v012.jar](archive/mtr-memory-sharing-neoforge-v012.jar) | 0.1.2 | neoforge 21.1.265 | [JSON](archive/mtr-memory-sharing-neoforge-v012.build.json) |
| [compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v030-nf248.jar](compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v030-nf248.jar) | 0.3.0 | neoforge 21.1.248 | [JSON](compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v030-nf248.build.json) |
| [compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v031-v6-nf248.jar](compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v031-v6-nf248.jar) | 0.3.1-v6 | neoforge 21.1.248 | [JSON](compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v031-v6-nf248.build.json) |
| [compatibility/performance-v6/mtr-memory-sharing-neoforge-v031-v6.jar](compatibility/performance-v6/mtr-memory-sharing-neoforge-v031-v6.jar) | 0.3.1-v6 | neoforge 21.1.265 | [JSON](compatibility/performance-v6/mtr-memory-sharing-neoforge-v031-v6.build.json) |
| [experiments/block-sharing/mtr-memory-sharing-neoforge-v024.jar](experiments/block-sharing/mtr-memory-sharing-neoforge-v024.jar) | 0.2.4 | neoforge 21.1.265 | [JSON](experiments/block-sharing/mtr-memory-sharing-neoforge-v024.build.json) |
| [experiments/bounded-text-cache/mtr-memory-sharing-neoforge-v030.jar](experiments/bounded-text-cache/mtr-memory-sharing-neoforge-v030.jar) | 0.3.0 | neoforge 21.1.265 | [JSON](experiments/bounded-text-cache/mtr-memory-sharing-neoforge-v030.build.json) |
| [experiments/compressed-text/mtr-memory-sharing-neoforge-v026.jar](experiments/compressed-text/mtr-memory-sharing-neoforge-v026.jar) | 0.2.6 | neoforge 21.1.265 | [JSON](experiments/compressed-text/mtr-memory-sharing-neoforge-v026.build.json) |
| [experiments/display-retention/archive/mtr-memory-sharing-neoforge-v021-interim.jar](experiments/display-retention/archive/mtr-memory-sharing-neoforge-v021-interim.jar) | 0.2.1 | neoforge 21.1.265 | [JSON](experiments/display-retention/archive/mtr-memory-sharing-neoforge-v021-interim.build.json) |
| [experiments/display-retention/mtr-memory-sharing-neoforge-v021.jar](experiments/display-retention/mtr-memory-sharing-neoforge-v021.jar) | 0.2.1 | neoforge 21.1.265 | [JSON](experiments/display-retention/mtr-memory-sharing-neoforge-v021.build.json) |
| [experiments/json-sharing/mtr-memory-sharing-neoforge-v022.jar](experiments/json-sharing/mtr-memory-sharing-neoforge-v022.jar) | 0.2.2 | neoforge 21.1.265 | [JSON](experiments/json-sharing/mtr-memory-sharing-neoforge-v022.build.json) |
| [experiments/packed-mesh/mtr-memory-sharing-neoforge-v020.jar](experiments/packed-mesh/mtr-memory-sharing-neoforge-v020.jar) | 0.2.0 | neoforge 21.1.265 | [JSON](experiments/packed-mesh/mtr-memory-sharing-neoforge-v020.build.json) |
| [experiments/segmented-reader/mtr-memory-sharing-neoforge-v027.jar](experiments/segmented-reader/mtr-memory-sharing-neoforge-v027.jar) | 0.2.7 | neoforge 21.1.265 | [JSON](experiments/segmented-reader/mtr-memory-sharing-neoforge-v027.build.json) |
| [experiments/segmented-unpack/archive/mtr-memory-sharing-neoforge-v028-initial.jar](experiments/segmented-unpack/archive/mtr-memory-sharing-neoforge-v028-initial.jar) | 0.2.8 | neoforge 21.1.265 | [JSON](experiments/segmented-unpack/archive/mtr-memory-sharing-neoforge-v028-initial.build.json) |
| [experiments/segmented-unpack/mtr-memory-sharing-neoforge-v028.jar](experiments/segmented-unpack/mtr-memory-sharing-neoforge-v028.jar) | 0.2.8 | neoforge 21.1.265 | [JSON](experiments/segmented-unpack/mtr-memory-sharing-neoforge-v028.build.json) |
| [experiments/shared-mesh/mtr-memory-sharing-neoforge-v023.jar](experiments/shared-mesh/mtr-memory-sharing-neoforge-v023.jar) | 0.2.3 | neoforge 21.1.265 | [JSON](experiments/shared-mesh/mtr-memory-sharing-neoforge-v023.build.json) |
| [experiments/source-displays/mtr-memory-sharing-neoforge-v025.jar](experiments/source-displays/mtr-memory-sharing-neoforge-v025.jar) | 0.2.5 | neoforge 21.1.265 | [JSON](experiments/source-displays/mtr-memory-sharing-neoforge-v025.build.json) |
| [experiments/streamed-digest/archive/string-charbuffer/mtr-memory-sharing-neoforge-v029.jar](experiments/streamed-digest/archive/string-charbuffer/mtr-memory-sharing-neoforge-v029.jar) | 0.2.9 | neoforge 21.1.265 | [JSON](experiments/streamed-digest/archive/string-charbuffer/mtr-memory-sharing-neoforge-v029.build.json) |
| [experiments/streamed-digest/mtr-memory-sharing-neoforge-v029.jar](experiments/streamed-digest/mtr-memory-sharing-neoforge-v029.jar) | 0.2.9 | neoforge 21.1.265 | [JSON](experiments/streamed-digest/mtr-memory-sharing-neoforge-v029.build.json) |
| [releases/mtr-memory-sharing-neoforge-v020.jar](releases/mtr-memory-sharing-neoforge-v020.jar) | 0.2.0 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v020.build.json) |
| [releases/mtr-memory-sharing-neoforge-v021.jar](releases/mtr-memory-sharing-neoforge-v021.jar) | 0.2.1 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v021.build.json) |
| [releases/mtr-memory-sharing-neoforge-v022.jar](releases/mtr-memory-sharing-neoforge-v022.jar) | 0.2.2 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v022.build.json) |
| [releases/mtr-memory-sharing-neoforge-v026.jar](releases/mtr-memory-sharing-neoforge-v026.jar) | 0.2.6 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v026.build.json) |
| [releases/mtr-memory-sharing-neoforge-v027.jar](releases/mtr-memory-sharing-neoforge-v027.jar) | 0.2.7 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v027.build.json) |
| [releases/mtr-memory-sharing-neoforge-v028.jar](releases/mtr-memory-sharing-neoforge-v028.jar) | 0.2.8 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v028.build.json) |
| [releases/mtr-memory-sharing-neoforge-v029.jar](releases/mtr-memory-sharing-neoforge-v029.jar) | 0.2.9 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v029.build.json) |
| [releases/mtr-memory-sharing-neoforge-v030.jar](releases/mtr-memory-sharing-neoforge-v030.jar) | 0.3.0 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge-v030.build.json) |
| [releases/mtr-memory-sharing-neoforge.jar](releases/mtr-memory-sharing-neoforge.jar) | 0.1.1 | neoforge 21.1.265 | [JSON](releases/mtr-memory-sharing-neoforge.build.json) |
| [releases/mtr-memory-sharing.jar](releases/mtr-memory-sharing.jar) | 0.1.1 | fabric  | [JSON](releases/mtr-memory-sharing.build.json) |

Exact SHA-256 values are in [index.json](index.json). Original manifests keep
their recording-time paths; [repository-origin.json](../repository-origin.json)
maps moved files while preserving evidence bytes.
