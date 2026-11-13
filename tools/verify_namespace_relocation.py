"""Compare a rebuilt companion with its historical baseline after namespace relocation."""
import argparse
import json
import pathlib
import struct
import tomllib
import zipfile

from build_vehicle_memory_mod import JAVA_PACKAGE, MOD_NAME, RESOURCE_ROOT, ROOT, digest, read_json, save_json


def relocated_class(data, previous, current):
    """Normalize constant-pool names for comparison; never rewrite a delivered JAR."""
    if data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('Invalid Java class file')
    count = struct.unpack_from('>H', data, 8)[0]
    output = bytearray(data[:10])
    offset, index = 10, 1
    widths = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4, 11: 4,
              12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}
    replacements = [(previous.encode(), current.encode()),
                    (previous.replace('.', '/').encode(), current.replace('.', '/').encode())]
    while index < count:
        tag = data[offset]
        output.append(tag)
        offset += 1
        if tag == 1:
            length = struct.unpack_from('>H', data, offset)[0]
            offset += 2
            value = data[offset:offset + length]
            offset += length
            for old, new in replacements:
                value = value.replace(old, new)
            output.extend(struct.pack('>H', len(value)))
            output.extend(value)
        else:
            width = widths[tag]
            output.extend(data[offset:offset + width])
            offset += width
            if tag in (5, 6):
                index += 1
        index += 1
    return bytes(output) + data[offset:]


def verify(baseline, candidate):
    mixin_file = 'mtr-memory-sharing.mixins.json'
    manifest = read_json(candidate.with_suffix('.build.json'))
    assert manifest['output_sha256'] == digest(candidate)
    assert manifest['java_package'] == JAVA_PACKAGE
    with zipfile.ZipFile(baseline) as old, zipfile.ZipFile(candidate) as new:
        before, after = json.loads(old.read(mixin_file)), json.loads(new.read(mixin_file))
        previous = before['package'].removesuffix('.mixin')
        current = after['package'].removesuffix('.mixin')
        assert current == JAVA_PACKAGE
        before['package'] = after['package']
        assert before == after, 'Mixin behavior changed'
        expected = {name.replace(previous.replace('.', '/'), current.replace('.', '/')):
                    relocated_class(old.read(name), previous, current)
                    for name in old.namelist() if name.endswith('.class')}
        classes = {name: new.read(name) for name in new.namelist() if name.endswith('.class')}
        assert expected.keys() == classes.keys(), 'Unexpected class set'
        assert all(expected[name] == data for name, data in classes.items()), 'Class changes exceed namespace relocation'
        assert all(name.startswith(current.replace('.', '/') + '/') for name in classes)
        for mixin in after['client']:
            assert after['package'].replace('.', '/') + '/' + mixin + '.class' in classes
        if 'fabric.mod.json' in new.namelist():
            metadata_file = 'fabric.mod.json'
            metadata = json.loads(new.read(metadata_file))
            icon = metadata.pop('icon')
            assert metadata['name'] == MOD_NAME
            baseline_metadata = json.loads(old.read(metadata_file))
            baseline_metadata['name'] = MOD_NAME
            assert metadata == baseline_metadata, 'Fabric identity or dependency changed'
        else:
            metadata_file = 'META-INF/neoforge.mods.toml'
            metadata = tomllib.loads(new.read(metadata_file).decode())
            icon = metadata['mods'][0].pop('logoFile')
            assert metadata['mods'][0].pop('logoBlur') is False
            assert metadata['mods'][0]['displayName'] == MOD_NAME
            baseline_metadata = tomllib.loads(old.read(metadata_file).decode())
            baseline_metadata['mods'][0]['displayName'] = MOD_NAME
            assert metadata == baseline_metadata, 'NeoForge identity or dependency changed'
        resources = {p.relative_to(RESOURCE_ROOT).as_posix(): p for p in RESOURCE_ROOT.rglob('*') if p.is_file()}
        for name, path in resources.items():
            assert new.read(name) == path.read_bytes(), name
            assert manifest['resources'][str(path.relative_to(ROOT))] == digest(path), name
        before_files = {n for n in old.namelist() if not n.endswith('/') and not n.endswith('.class')}
        after_files = {n for n in new.namelist() if not n.endswith('/') and not n.endswith('.class')}
        assert after_files == before_files | resources.keys(), 'Unexpected packaged files'
        for name in before_files - {metadata_file, mixin_file}:
            assert new.read(name) == old.read(name), name
        pack = json.loads(new.read('pack.mcmeta'))['pack']
        assert pack['pack_format'] == 34, 'Minecraft 1.21.1 uses resource pack format 34'
        description = pack['description']['translate']
        languages = [n for n in resources if '/lang/' in n and n.endswith('.json')]
        assert languages and all(json.loads(new.read(n)).get(description) for n in languages)
        png = new.read(icon)
        assert icon == 'pack.png' and png[:8] == b'\x89PNG\r\n\x1a\n'
        width, height = struct.unpack_from('>II', png, 16)
        assert width == height == 512
    return {'baseline_sha256': digest(baseline), 'candidate_sha256': digest(candidate),
            'previous_package': previous, 'java_package': current,
            'classes_equal_after_namespace_normalization': len(classes),
            'mixin_targets_present': len(after['client']), 'loader_identity_and_dependencies_unchanged': True,
            'resource_files_verified': sorted(resources), 'pack_format': pack['pack_format'],
            'localized_description_key': description, 'icon_dimensions': [width, height],
            'icon_sha256': digest(RESOURCE_ROOT / icon)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=pathlib.Path, required=True)
    parser.add_argument('--candidate', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = verify(args.baseline, args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, result)
    print(f"Verified {result['classes_equal_after_namespace_normalization']} relocated classes, Mixins and pack resources.")


if __name__ == '__main__':
    main()
