# Build MTR Memory Saver

Run these commands from this repository root. The build needs Python 3.11+, a
Java 21 JDK, and a prepared Minecraft 1.21.1 client with the audited MTR release
and matching loader libraries. No resource-pack project Python modules are needed.

Current builds use `site.benli06` (`site.benli06.mixin` for Mixins). The unchanged
mod ID is `mtr_memory_sharing`. Historical delivery JARs use the previous package;
check out revision `37f3bb7` to reproduce those original member payloads. Existing
runtime acceptance describes those historical binaries. New builds record their
Java package and resource hashes in the adjacent build manifest.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest discover -s tools -p 'test_*.py'

$instance = (Resolve-Path -LiteralPath '<prepared Minecraft instance>').Path
$marker = Get-Content -LiteralPath "$instance/vehicle-test-instance.json" -Raw | ConvertFrom-Json
$javac = Join-Path (Split-Path $marker.java) 'javac.exe'
```

The instance is an external build input. Its `vehicle-test-instance.json` records
`instance` (the absolute instance path), `mod_loader` (`fabric` or `neoforge`),
`loader` (the loader version), `version` (the launcher version ID), and `target`
with `minecraft` and `mtr` versions. Existing test fixtures also record `java` for
the example above and `pid` while running. The builder reads the active version
JSON, inherited libraries, and game JARs from that instance. Fabric requires its
existing intermediary remapped client. NeoForge requires the active patched client,
matching NeoForm SRG game JAR, universal loader JAR, and launch module libraries.
Use the existing prepared fixture or prepare these inputs with the corresponding
launcher; the build does not download or launch Minecraft.

## Official MTR, bounded cache v0.3.0

```powershell
.venv/Scripts/python.exe -X utf8 tools/build_vehicle_memory_mod.py `
  --instance $instance --javac $javac `
  --packed-meshes --prune-displays --share-json --compress-texts `
  --segment-text-reads --segment-text-unpacks --stream-text-digests --bound-text-cache `
  --output dist/local/mtr-memory-sharing-neoforge-v030.jar
```

Use the prepared instance for the desired NeoForge version (21.1.248 or 21.1.265).
The builder keeps the exact release and active-loader checks and writes the actual
minimum loader version into the companion metadata. Refer to the matching
[installation guide](compatibility/neoforge-21.1.248/README.md) before installing.

## Performance v6, compatibility v0.3.1-v6

Use the prepared instance containing the exact audited custom MTR release. Add
`--performance-v6 --mtr-jar '<exact custom MTR JAR>'` to all v0.3.0 flags above
and select a different output, such as `dist/local/mtr-memory-sharing-neoforge-v031-v6.jar`.
The builder verifies the release SHA-256; changing version metadata alone cannot
substitute for the compatibility source. See the [v6 guide](compatibility/performance-v6/README.md).

## Baseline and other variants

Without feature flags, the builder produces the historical v0.1.1 baseline for
the instance's Fabric or NeoForge loader. Its default output is in `dist/local/`.
Use `--help` for the existing experimental flags and their prerequisites.
The source under `src/experiments/` is selected explicitly; archived alternatives
are not compiled accidentally. All compiled intermediates go into `build/`.

Every output has an adjacent `.build.json` recording source, game, release and JAR
hashes. New source paths are relative to this repository. The existing manifests
under `dist/` retain their original paths and bytes; use
[repository-origin.json](repository-origin.json) to resolve moved inputs.
The [artifact index](dist/README.md) lists preserved deliveries. JARs, `build/`,
the virtual environment and `dist/local/` are ignored by Git. Historical delivery
manifests remain tracked; a fresh clone needs a rebuild or separately supplied JARs.

`--install-test` is optional and only installs into the specified stopped, marked
instance. Ordinary builds do not install anything. JAR container timestamps may
differ between builds, so compare member payloads when verifying a rebuild.

The resource-pack project's `tools/build_vehicle_memory_mod.py` remains a small
compatibility entry point for its fixture/audit scripts. Their historical examples
run from that project's root; standalone builds use the commands on this page.
Runtime evidence and integration tooling retain their original fixture scope.

## Pack metadata and icon

All files in `src/main/resources/` are copied to the JAR root during every build.
`pack.mcmeta` declares resource pack format 34 for the supported Minecraft 1.21.1
target. Its translated description is supplied by `assets/mtr_memory_sharing/lang/`;
add locale files there to extend translations. `pack.png` is a 512 × 512 RGBA PNG
used by the pack and both loader metadata files.

The icon is original geometric artwork: a train framed by memory-chip pins, with
railway tracks and no language-specific lettering. Its editable source is
`tools/render_pack_icon.py`. Pillow is optional and is only needed to regenerate it:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-artwork.txt
.venv/Scripts/python.exe tools/render_pack_icon.py
```

The committed PNG is used directly by normal builds; icon-generation dependencies
are not required to build or run the mod.

To verify a new build against its matching historical JAR, use:

```powershell
.venv/Scripts/python.exe tools/verify_namespace_relocation.py `
  --baseline '<matching historical JAR>' --candidate '<new JAR>' `
  --output .cache/namespace-verification.json
```

The verifier compares actual class files after normalizing constant-pool package
names, checks every declared Mixin class, and verifies loader metadata, translations,
icon and resource hashes. It changes no JAR bytes. Historical external Java audit
tools target the earlier namespace; their original results retain that scope.
The [2026-11-11 build checks](evidence/namespace-branding-20261111.json) cover both
baseline loaders and official/v6 NeoForge 21.1.248 with the current namespace.
