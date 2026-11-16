# Install MTR Memory Saver

Build or obtain the bundle for your exact target in [SUPPORT.md](SUPPORT.md).
Inside it, put the single companion JAR in the Minecraft client's `mods/` directory,
alongside the matching MTR and NeoForge releases. Remove an older memory companion
before installing the new one. The mod ID remains `mtr_memory_sharing`.

Official MTR beta.2 and custom Performance v6 require different companions. Their
version labels alone do not identify compatible binaries. The companion checks the
loaded MTR SHA-256 before applying its Mixins and declares an exact NeoForge version.
An incompatible target should produce an explicit startup error, not guessed hooks.

Resource packs belong in `resourcepacks/`, not in the mod JAR. This companion changes
loading/storage and does not repair missing model, sound, doorway or floor data.

To roll back, close Minecraft and replace the new companion with your previous
matching JAR, or remove it. Do not install two companion versions together.
The original MTR JAR and authored resource packs need no modification.

The 3 GiB and scheduler settings in historical reports belong to their tested
fixtures. New 0.4.x candidates need their own runtime acceptance; no global JVM
scheduler setting is added to the new build's client run automatically.
