"""Build the version-pinned client memory companion and optionally install in the test client."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import uuid
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
JAVA_PACKAGE = 'site.benli06'
RESOURCE_ROOT = ROOT / 'src/main/resources'


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def save_json(path, data):
    pathlib.Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path, algorithm='sha256'):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


RELEASES = {
    'fabric': '5da075f7d63daea89da17348ace0959a0c216cbaf14a322d063a64bec44aae94',
    'neoforge': 'ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa',
}
VERSION = '0.1.1'
PERFORMANCE_V6 = {
    'version': '4.1.0-beta.2-mc1.21.1-performance-v6',
    'sha256': '8bd419bd798c2ab2fa03e08850409387804fdeb2e4f2987c66b9984236263585',
}


def runtime_libraries(instance):
    """Use the launcher's active inherited version, excluding installer-only JARs."""
    from minecraft_launcher_lib._helper import inherit_json
    from minecraft_launcher_lib.command import get_libraries
    marker = read_json(instance / 'vehicle-test-instance.json')
    version = marker['version']
    data = read_json(instance / 'versions' / version / (version + '.json'))
    if 'inheritsFrom' in data:
        data = inherit_json(data, str(instance))
    libraries = [pathlib.Path(item) for item in get_libraries(data, str(instance)).split(os.pathsep) if item]
    if marker.get('mod_loader') == 'neoforge':
        # ModLauncher discovers these separately. The client patch contains only changed
        # classes, so the matching NeoForm SRG game classes are also required offline.
        game_args = data['arguments']['game']
        neoform = game_args[game_args.index('--fml.neoFormVersion') + 1]
        minecraft = game_args[game_args.index('--fml.mcVersion') + 1]
        neoforge = game_args[game_args.index('--fml.neoForgeVersion') + 1]
        required = [instance / 'libraries/net/minecraft/client' / f'{minecraft}-{neoform}' / f'client-{minecraft}-{neoform}-srg.jar',
                    instance / 'libraries/net/neoforged/neoforge' / neoforge / f'neoforge-{neoforge}-universal.jar']
        if any(not path.is_file() for path in required):
            raise ValueError('Active NeoForge game/runtime artifacts are missing.')
        libraries = required + libraries
        jvm = data['arguments']['jvm']
        for i, arg in enumerate(jvm[:-1]):
            if arg in ('-p', '--module-path'):
                module_paths = jvm[i + 1].replace('${library_directory}', str(instance / 'libraries')).replace('${classpath_separator}', os.pathsep)
                libraries = [pathlib.Path(item) for item in module_paths.split(os.pathsep)] + libraries
    return list(dict.fromkeys(path for path in libraries if path.is_file()))


def minecraft_classpath(instance, loader):
    if loader == 'fabric':
        game = list((instance / '.fabric/remappedJars').glob('*/client-intermediary.jar'))
        if len(game) != 1:
            raise ValueError('One Fabric remapped Minecraft JAR required.')
        return game
    # Other installed loader versions may remain in the library cache. Compile
    # against the marked launch version, never a different cached client patch.
    marker = read_json(instance / 'vehicle-test-instance.json')
    version = marker['loader']
    data = read_json(instance / 'versions' / marker['version'] / (marker['version'] + '.json'))
    game_args = data['arguments']['game']
    active_version = game_args[game_args.index('--fml.neoForgeVersion') + 1]
    if active_version != version:
        raise ValueError('Marked NeoForge loader differs from the active launch version.')
    jar = instance / 'libraries/net/neoforged/neoforge' / version / f'neoforge-{version}-client.jar'
    if not jar.is_file():
        raise ValueError('Active NeoForge patched Minecraft JAR is missing.')
    with zipfile.ZipFile(jar) as archive:
        if 'net/minecraft/resources/ResourceLocation.class' not in archive.namelist():
            raise ValueError('Active NeoForge client patch lacks the required Minecraft classes.')
    return [jar]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance', type=pathlib.Path, required=True, help='Prepared Minecraft instance containing vehicle-test-instance.json and its runtime libraries.')
    p.add_argument('--javac', type=pathlib.Path, required=True)
    p.add_argument('--output', type=pathlib.Path)
    p.add_argument('--install-test', action='store_true')
    p.add_argument('--performance-v6', action='store_true', help='Build the explicit v0.3.1-v6 compatibility variant for the audited custom release.')
    p.add_argument('--mtr-jar', type=pathlib.Path, help='Exact custom release JAR; required with --performance-v6.')
    p.add_argument('--packed-meshes', action='store_true', help='Build the experimental lossless packed-mesh NeoForge variant into an explicit output file.')
    p.add_argument('--prune-displays', action='store_true', help='Build the NeoForge packed variant with property-selected display retention.')
    p.add_argument('--share-json', action='store_true', help='Share read-only parsed vehicle configuration JSON while keeping independent readers and build caches.')
    p.add_argument('--share-meshes', action='store_true', help='Use immutable packed source snapshots for transformed meshes without recompressing vertex copies.')
    p.add_argument('--intern-blocks', action='store_true', help='Share content-identical immutable compressed vertex blocks during resource registration.')
    p.add_argument('--source-displays', action='store_true', help='Select actual vehicle DISPLAY names before parsing, retaining raw source display data only for those names.')
    p.add_argument('--compress-texts', action='store_true', help='Keep exact resource text in a compressed registration cache instead of large source Strings.')
    p.add_argument('--segment-text-reads', action='store_true', help='Decode native resource text in bounded segments and join once, preserving the native stream owner.')
    p.add_argument('--segment-text-unpacks', action='store_true', help='Restore compressed text in bounded UTF-16 segments without a complete temporary char array.')
    p.add_argument('--stream-text-digests', action='store_true', help='Hash large resource text through bounded UTF-8 encoding while preserving exact shared-cache keys.')
    p.add_argument('--bound-text-cache', action='store_true', help='Bound compressed resource-text retention by heap size, rereading evicted inputs as needed.')
    args = p.parse_args()
    instance = args.instance.resolve()
    marker = read_json(instance / 'vehicle-test-instance.json')
    if pathlib.Path(marker['instance']).resolve() != instance:
        raise ValueError('Instance identity mismatch.')
    loader = marker.get('mod_loader', 'fabric')
    target_version = PERFORMANCE_V6['version'] if args.performance_v6 else '4.1.0-beta.2'
    if loader not in RELEASES or marker['target'] != {'minecraft': '1.21.1', 'mtr': target_version}:
        raise ValueError('Unsupported loader or target release.')
    if args.performance_v6 and (loader != 'neoforge' or not args.output or not args.mtr_jar
                               or not args.bound_text_cache or args.share_meshes or args.source_displays):
        p.error('--performance-v6 requires NeoForge, explicit --output/--mtr-jar and the bounded v0.3.0 configuration without other mesh/source experiments.')
    if args.mtr_jar and not args.performance_v6:
        p.error('--mtr-jar is only supported for the explicit audited custom variant.')
    if args.packed_meshes and (loader != 'neoforge' or args.output is None):
        p.error('--packed-meshes requires NeoForge and an explicit --output.')
    if args.prune_displays and not args.packed_meshes:
        p.error('--prune-displays requires --packed-meshes.')
    if args.share_json and not args.prune_displays:
        p.error('--share-json requires --prune-displays.')
    if args.share_meshes and not args.share_json:
        p.error('--share-meshes requires --share-json.')
    if args.intern_blocks and not args.share_meshes:
        p.error('--intern-blocks requires --share-meshes.')
    if args.source_displays and not args.share_json:
        p.error('--source-displays requires --share-json.')
    if args.compress_texts and not args.share_json:
        p.error('--compress-texts requires --share-json.')
    if args.segment_text_reads and not args.compress_texts:
        p.error('--segment-text-reads requires --compress-texts.')
    if args.segment_text_unpacks and not args.segment_text_reads:
        p.error('--segment-text-unpacks requires --segment-text-reads.')
    if args.stream_text_digests and (not args.segment_text_unpacks or args.source_displays):
        p.error('--stream-text-digests requires --segment-text-unpacks and the standard shared source cache.')
    if args.bound_text_cache and not args.stream_text_digests:
        p.error('--bound-text-cache requires --stream-text-digests.')
    version = '0.2.9' if args.stream_text_digests else '0.2.8' if args.segment_text_unpacks else '0.2.7' if args.segment_text_reads else '0.2.6' if args.compress_texts else '0.2.5' if args.source_displays else '0.2.4' if args.intern_blocks else '0.2.3' if args.share_meshes else '0.2.2' if args.share_json else '0.2.1' if args.prune_displays else '0.2.0' if args.packed_meshes else VERSION
    if args.bound_text_cache:
        version = '0.3.0'
    if args.performance_v6:
        version = '0.3.1-v6'
    if args.install_test and marker.get('pid'):
        run = subprocess.run(['pwsh', '-NoProfile', '-Command',
                              f'Get-Process -Id {int(marker["pid"])} -ErrorAction SilentlyContinue'],
                             capture_output=True)
        if run.stdout.strip():
            raise ValueError('Close the recorded test client before installing the companion.')
    game = minecraft_classpath(instance, loader)
    mtr = [args.mtr_jar.resolve() if args.mtr_jar else instance / 'mods' / f"MTR-{loader}-{marker['target']['mtr']}+{marker['target']['minecraft']}.jar"]
    expected = PERFORMANCE_V6['sha256'] if args.performance_v6 else RELEASES[loader]
    if digest(mtr[0]) != expected:
        raise ValueError('The companion requires the exact audited target release fingerprint.')
    build = ROOT / 'build' / str(uuid.uuid4())
    build.mkdir(parents=True)
    classpath = os.pathsep.join(map(str, dict.fromkeys(game + mtr + runtime_libraries(instance))))
    common_root = ROOT / 'src/main/java'
    platform_root = ROOT / 'src/platform' / loader / 'java'
    platform_sources = {source.relative_to(platform_root): source
                        for source in sorted(platform_root.rglob('*.java'))}
    sources = [source for source in sorted(common_root.rglob('*.java'))
               if source.relative_to(common_root) not in platform_sources] + list(platform_sources.values())
    if args.packed_meshes:
        experiment = ROOT / 'src/experiments/packed-mesh'
        sources += sorted((experiment / 'java').rglob('*.java')) + sorted((experiment / 'platform' / loader / 'java').rglob('*.java'))
    if args.prune_displays:
        sources = [s for s in sources if s.name not in ('SharedBlockbenchCache.java', 'SharedBlockbenchLoader.java')]
        sources += sorted((ROOT / 'src/experiments/display-retention/java').rglob('*.java'))
    if args.share_json:
        sources += sorted((ROOT / 'src/experiments/json-sharing/java').rglob('*.java'))
    if args.share_meshes:
        sources = [s for s in sources if s.name != 'PackedVertices.java']
        variant = 'block-sharing' if args.intern_blocks else 'shared-mesh'
        sources += sorted((ROOT / 'src/experiments' / variant / 'java').rglob('*.java'))
    if args.source_displays:
        sources = [s for s in sources if s.name not in ('SharedBlockbenchCache.java', 'SharedBlockbenchLoader.java')]
        sources += sorted((ROOT / 'src/experiments/source-displays/java').rglob('*.java'))
    if args.compress_texts:
        sources += sorted((ROOT / 'src/experiments/compressed-text/java').rglob('*.java'))
    if args.segment_text_reads:
        sources += sorted((ROOT / 'src/experiments/segmented-reader/java').rglob('*.java'))
    if args.segment_text_unpacks:
        sources = [s for s in sources if s.name != 'CompressedResourceTextCache.java']
        sources += sorted((ROOT / 'src/experiments/segmented-unpack/java').rglob('*.java'))
    if args.stream_text_digests:
        sources = [s for s in sources if s.name not in ('SharedBlockbenchCache.java', 'VehicleJsonCache.java')]
        sources += sorted((ROOT / 'src/experiments/streamed-digest/java').rglob('*.java'))
    if args.bound_text_cache:
        sources = [s for s in sources if s.name not in ('CompressedResourceTextCache.java', 'CompressedResourceTextMixin.java')]
        sources += sorted((ROOT / 'src/experiments/bounded-text-cache/java').rglob('*.java'))
    if args.performance_v6:
        compatibility_sources = sorted((ROOT / 'src/compatibility/performance-v6/java').rglob('*.java'))
        replaced = {s.name for s in compatibility_sources} | {'VertexColorMixin.java'}
        sources = [s for s in sources if s.name not in replaced] + compatibility_sources
    compiled = subprocess.run([str(args.javac), '-J-Duser.language=en', '-proc:none', '--release', '21', '-classpath', classpath,
                               '-d', str(build), *map(str, sources)])
    if compiled.returncode:
        raise SystemExit(f'javac failed with exit code {compiled.returncode}; no artifact installed.')
    resources = sorted(path for path in RESOURCE_ROOT.rglob('*') if path.is_file())
    for resource in resources:
        target = build / resource.relative_to(RESOURCE_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resource, target)
    if loader == 'fabric':
        save_json(build / 'fabric.mod.json', {
            'schemaVersion': 1, 'id': 'mtr_memory_sharing', 'version': version,
            'name': 'MTR Memory Sharing', 'environment': 'client',
            'authors': ['A-BenLi06'], 'license': 'MIT',
            'icon': 'pack.png',
            'mixins': ['mtr-memory-sharing.mixins.json'],
            'depends': {'fabricloader': '>=' + marker['loader'], 'java': '>=21',
                        'minecraft': '=' + marker['target']['minecraft'], 'mtr': '=' + marker['target']['mtr']},
        })
    else:
        metadata = build / 'META-INF/neoforge.mods.toml'
        metadata.parent.mkdir(parents=True)
        metadata.write_text('''modLoader = "lowcodefml"
loaderVersion = "[4,)"
license = "MIT"

[[mods]]
modId = "mtr_memory_sharing"
version = "''' + version + '''"
displayName = "MTR Memory Sharing"
authors = "A-BenLi06"
logoFile = "pack.png"
logoBlur = false
description = "Shares identical parsed vehicle model inputs across independent vehicle loaders."

[[dependencies.mtr_memory_sharing]]
modId = "neoforge"
type = "required"
versionRange = "[''' + marker['loader'] + ''',)"
ordering = "NONE"
side = "CLIENT"

[[dependencies.mtr_memory_sharing]]
modId = "minecraft"
type = "required"
versionRange = "[''' + marker['target']['minecraft'] + ''']"
ordering = "NONE"
side = "CLIENT"

[[dependencies.mtr_memory_sharing]]
modId = "mtr"
type = "required"
versionRange = "[''' + marker['target']['mtr'] + ''']"
ordering = "AFTER"
side = "CLIENT"

[[mixins]]
config = "mtr-memory-sharing.mixins.json"
''', encoding='utf-8')
    save_json(build / 'mtr-memory-sharing.mixins.json', {
        'required': True, 'minVersion': '0.8', 'package': JAVA_PACKAGE + '.mixin',
        'compatibilityLevel': 'JAVA_21', 'client': [
            'ModelLoaderAccess', 'ModelLoaderCompletionMixin', 'VehicleModelFactoryMixin',
            'ResourceReloadMixin'] + ([] if args.performance_v6 else ['VertexColorMixin'])
            + (['V6LoaderLifecycleMixin'] if args.performance_v6 else [])
            + (['PackedModelGroupMixin'] if args.packed_meshes else [])
            + (['DisplayPartAccess', 'DisplaySelectionMixin', 'SourceLifetimeMixin'] if args.prune_displays else [])
            + (['VehicleJsonCacheMixin', 'VehicleJsonEpochMixin'] if args.share_json else [])
            + (['PackedBlockLifetimeMixin'] if args.intern_blocks else [])
            + (['VehicleSourceSelectionMixin', 'SourceDisplayPartsMixin', 'SourceParseCompletionMixin'] if args.source_displays else [])
            + (['CompressedResourceTextMixin'] if args.compress_texts else [])
            + (['SegmentedResourceTextMixin'] if args.segment_text_reads else []), 'injectors': {'defaultRequire': 1},
    })
    default_name = 'mtr-memory-sharing.jar' if loader == 'fabric' else 'mtr-memory-sharing-neoforge.jar'
    output = (args.output or ROOT / 'dist/local' / default_name).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(args.javac.with_name('jar.exe')), '--create', '--file', str(output),
                    '-C', str(build), '.'], check=True)
    if args.install_test:
        shutil.copyfile(output, instance / 'mods' / default_name)
    save_json(output.with_suffix('.build.json'), {
        'target': marker['target'], 'version': version, 'packed_meshes': args.packed_meshes,
        'prune_displays': args.prune_displays,
        'share_json': args.share_json,
        'share_meshes': args.share_meshes,
        'intern_blocks': args.intern_blocks,
        'source_displays': args.source_displays,
        'compress_texts': args.compress_texts,
        'segment_text_reads': args.segment_text_reads,
        'segment_text_unpacks': args.segment_text_unpacks,
        'stream_text_digests': args.stream_text_digests,
        'bound_text_cache': args.bound_text_cache,
        **({'compatibility_target': 'performance-v6'} if args.performance_v6 else {}),
        'mod_loader': loader, 'loader_version': marker['loader'],
        'minecraft_jar_sha256': digest(game[0]), 'release_jar_sha256': expected,
        'output_sha256': digest(output), 'sources': {str(s.relative_to(ROOT)): digest(s) for s in sources},
        'java_package': JAVA_PACKAGE,
        'resources': {str(r.relative_to(ROOT)): digest(r) for r in resources},
        'installed_test': args.install_test,
    })
    print(f'Built {output}; installed in test client: {args.install_test}', flush=True)


if __name__ == '__main__':
    main()
