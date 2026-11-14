"""Static official/full-pack reference; no client, pack or world mutation."""
import collections
import contextlib
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
CATALOG = ROOT.parent / '[MTR4.1原生目录]产物/catalog.json'
MTR = ROOT / '.cache/dependencies/mtr-ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa.jar'
JAVAP = pathlib.Path('C:/Users/ben_l/.gradle/jdks/eclipse_adoptium-21-amd64-windows.2/bin/javap.exe')
REGISTRIES = ('assets/mtr/mtr_custom_resources.json', 'assets/mtr/mtr_custom_resources_pending_migration.json')
MODEL_FIELDS = ('models', 'bogie1Models', 'bogie2Models')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def resource_path(identifier):
    if not identifier:
        return None
    if ':' not in identifier:
        raise ValueError('Do not infer an unauthored namespace: ' + identifier)
    namespace, path = identifier.split(':', 1)
    return 'assets/' + namespace + '/' + path


def methods(source, needles):
    lines = source.splitlines()
    selected = []
    for index, line in enumerate(lines):
        if line.startswith('  ') and not line.startswith('    ') and any(x in line for x in needles):
            end = next((x for x in range(index + 1, len(lines))
                        if lines[x].startswith('  ') and not lines[x].startswith('    ') and lines[x].strip()), len(lines))
            selected.extend(lines[index:end])
    return '\n'.join(selected) + '\n'


def main():
    if (OUT / 'assessment.json').exists():
        raise ValueError('Refuse to overwrite completed reference evidence.')
    catalog = json.loads(CATALOG.read_text(encoding='utf-8-sig'))
    assert catalog['passed'] is True and len(catalog['packs']) == 16
    sources = [{'path': str(MTR), 'filename': MTR.name, 'kind': 'official_mtr', 'sha256': digest(MTR), 'priority': 0}]
    assert sources[0]['sha256'] == 'ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa'
    for index, pack in enumerate(catalog['packs'], 1):
        path = CATALOG.parent / pack['output']
        actual = digest(path)
        assert actual == pack['output_sha256'], path
        sources.append({'path': str(path), 'filename': path.name, 'kind': 'catalogue_pack', 'sha256': actual, 'priority': index})
        print('Verified archive', index, flush=True)
    sys.path.insert(0, str(ROOT.parent / 'tools'))
    from vehicle_catalog_map import resolve
    formations = {family: {str(count): resolve(catalog, family, count, 'en_us') for count in (2, 6)}
                  for family in ('dc01', 'dc01_update')}
    origins = collections.defaultdict(list)
    declarations = []
    manifests = []
    effective = {}
    definitions = {}
    properties = {}
    missing = []
    features = []
    with contextlib.ExitStack() as stack:
        archives = [stack.enter_context(zipfile.ZipFile(source['path'])) for source in sources]
        for index, archive in enumerate(archives):
            if 'pack.mcmeta' in archive.namelist():
                meta = json.loads(archive.read('pack.mcmeta').decode('utf-8-sig'))
                assert not meta.get('filter'), 'Resource filters need explicit simulation.'
            for info in archive.infolist():
                if info.filename.startswith('assets/') and not info.is_dir():
                    origins[info.filename].append({'source_index': index, 'bytes': info.file_size, 'compressed_bytes': info.compress_size, 'crc32': f'{info.CRC:08x}'})
        # Native loader processes the whole main stack first, then the pending stack.
        for registry in REGISTRIES:
            for index, archive in enumerate(archives):
                if registry not in archive.namelist():
                    continue
                raw = archive.read(registry)
                data = json.loads(raw.decode('utf-8-sig'))
                legacy = 'custom_trains' in data or 'custom_signs' in data
                assert not data.get('custom_trains'), 'Legacy conversion requires a separate native oracle.'
                rows = [] if legacy else data.get('vehicles', [])
                manifests.append({'source_index': index, 'resource': registry, 'sha256': hashlib.sha256(raw).hexdigest(), 'native_vehicle_rows': len(rows), 'legacy_branch': legacy, 'keys': list(data)})
                for ordinal, definition in enumerate(rows):
                    key = (definition['transportMode'], definition['id'])
                    row = {'transport_mode': key[0], 'vehicle_id': key[1], 'source_index': index, 'manifest': registry, 'ordinal': ordinal, 'definition_sha256': hashlib.sha256(canonical(definition)).hexdigest()}
                    declarations.append(row)
                    effective[key] = row
                    definitions[key] = definition
        keys = sorted(effective)
        assert sum(row['native_vehicle_rows'] for row in manifests if row['source_index']) == catalog['totals']['native_entries']
        for family_counts in formations.values():
            for cars in family_counts.values():
                assert all(row['status'] == 'repaired' and ('TRAIN', row['id']) in effective for row in cars)
        references = collections.defaultdict(list)
        for key in keys:
            definition = definitions[key]
            combined = {'display': False, 'floor': False, 'doorway': False, 'door_movement': False, 'door_condition': False}
            model_rows = []
            for field in MODEL_FIELDS:
                for ordinal, model in enumerate(definition.get(field, [])):
                    path = resource_path(model.get('modelResource'))
                    prop_path = resource_path(model.get('modelPropertiesResource'))
                    if path:
                        references[path].append({'transport_mode': key[0], 'vehicle_id': key[1], 'model_list': field, 'ordinal': ordinal})
                        if path not in origins:
                            missing.append({'kind': 'model', 'resource': path, 'vehicle_id': key[1]})
                    prop = None
                    if prop_path and prop_path not in properties:
                        if prop_path in origins:
                            origin = origins[prop_path][-1]
                            raw = archives[origin['source_index']].read(prop_path)
                            data = json.loads(raw.decode('utf-8-sig'))
                            parts = data.get('parts', [])
                            flags = {'display': any(p.get('type') == 'DISPLAY' for p in parts),
                                     'floor': any(p.get('type') == 'FLOOR' for p in parts),
                                     'doorway': any(p.get('type') == 'DOORWAY' for p in parts),
                                     'door_movement': any(p.get('doorXMultiplier', 0) != 0 or p.get('doorZMultiplier', 0) != 0 for p in parts),
                                     'door_condition': any(p.get('condition') in ('DOORS_OPENED', 'DOORS_CLOSED') for p in parts)}
                            properties[prop_path] = {'source_index': origin['source_index'], 'sha256': hashlib.sha256(raw).hexdigest(), 'parts': len(parts), 'features': flags,
                                                     'part_types_authored': sorted({p.get('type', 'NORMAL') for p in parts}),
                                                     'display_types_authored': sorted({p.get('displayType', 'DESTINATION') for p in parts if p.get('type') == 'DISPLAY'}),
                                                     'door_animation_types_authored': sorted({p.get('doorAnimationType', 'STANDARD') for p in parts if p.get('doorXMultiplier', 0) != 0 or p.get('doorZMultiplier', 0) != 0})}
                        else:
                            properties[prop_path] = None
                            missing.append({'kind': 'model_properties', 'resource': prop_path, 'vehicle_id': key[1]})
                    if prop_path:
                        prop = properties[prop_path]
                    if prop:
                        for feature, present in prop['features'].items():
                            combined[feature] |= present
                    model_rows.append({'model_list': field, 'ordinal': ordinal, 'model_resource': path, 'model_source_index': origins[path][-1]['source_index'] if path in origins else None, 'properties_resource': prop_path, 'properties_source_index': prop['source_index'] if prop else None})
            features.append({'transport_mode': key[0], 'vehicle_id': key[1], 'definition_source_index': effective[key]['source_index'], 'features': combined, 'models': model_rows})
        bbmodels = []
        for number, path in enumerate(sorted(p for p in origins if p.endswith('.bbmodel')), 1):
            origin = origins[path][-1]
            with archives[origin['source_index']].open(path) as stream:
                fingerprint = hashlib.file_digest(stream, 'sha256').hexdigest()
            bbmodels.append({'resource': path, **origin, 'sha256': fingerprint, 'reference_count': len(references[path]), 'references': references[path], 'provider_count': len(origins[path])})
            if number % 100 == 0:
                print('Hashed native model resource', number, flush=True)
    declaration_keys = collections.Counter((row['transport_mode'], row['vehicle_id']) for row in declarations)
    duplicates = [{'transport_mode': key[0], 'vehicle_id': key[1], 'declarations': [row for row in declarations if (row['transport_mode'], row['vehicle_id']) == key], 'winner': effective[key]} for key, count in declaration_keys.items() if count > 1]
    per_mode = dict(collections.Counter(key[0] for key in keys))
    largest_all = max(bbmodels, key=lambda row: row['bytes'])
    referenced = [row for row in bbmodels if row['reference_count']]
    largest_used = max(referenced, key=lambda row: row['bytes'])
    representative = {}
    for row in features:
        flags = ','.join(key for key, value in row['features'].items() if value)
        representative.setdefault(row['transport_mode'] + ':' + flags, row)
    dc01_ids = {row['id'] for rows in formations['dc01'].values() for row in rows}
    assessment = {'timestamp': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  'status': 'static_reference_only_runtime_pending', 'catalogue': {'path': str(CATALOG), 'sha256': digest(CATALOG), 'totals': catalog['totals']},
                  'sources': sources, 'manifest_rows': manifests,
                  'identity_policy': 'Effective lookup key is (transportMode,id); list retains all declarations; resources resolve highest-priority provider. Main registry stacks precede pending stacks.',
                  'expected_list_registration_count': len(declarations), 'expected_effective_registration_count': len(keys), 'expected_distinct_id_strings': len({key[1] for key in keys}),
                  'effective_by_transport_mode': per_mode, 'duplicate_registration_keys': duplicates,
                  'bbmodel_physical_entries': sum(1 for p, o in origins.items() if p.endswith('.bbmodel') for _ in o), 'bbmodel_unique_resource_paths': len(bbmodels),
                  'bbmodel_referenced_by_effective_vehicles': len(referenced), 'bbmodel_unreferenced_by_effective_vehicles': len(bbmodels) - len(referenced),
                  'bbmodel_effective_uncompressed_bytes': sum(row['bytes'] for row in bbmodels), 'largest_bbmodel_any_asset': largest_all, 'largest_bbmodel_referenced_vehicle_asset': largest_used,
                  'model_property_unique_resources': len(properties), 'static_vehicle_feature_counts': {name: sum(row['features'][name] for row in features) for name in features[0]['features']},
                  'static_property_feature_counts': {name: sum(bool(row and row['features'][name]) for row in properties.values()) for name in features[0]['features']},
                  'referenced_resources_missing': missing, 'representative_feature_combinations': list(representative.values()),
                  'dc01_representative_features': [row for row in features if row['vehicle_id'] in dc01_ids],
                  'limits': 'ZIP/static JSON reference only. Explicit authored part fields do not prove rendered geometry, display text, native bounds, opening side, boarding or successful native parsing. Unreferenced means no effective vehicle declaration reference, not no use by signs/objects/scripts. Byte counts are ZIP payload sizes, not decoded UTF-16 or expanded model/heap/GPU sizes.'}
    write('expected-identities.json', [{'transport_mode': key[0], 'vehicle_id': key[1], **effective[key]} for key in keys])
    write('all-registration-declarations.json', declarations)
    write('bbmodel-resources.json', bbmodels)
    write('model-properties.json', properties)
    write('vehicle-feature-reference.json', features)
    write('dc01-formations.json', formations)
    write('resource-overrides.json', {path: rows for path, rows in origins.items() if len(rows) > 1})
    for classname, needles, filename in [('org.mtr.client.CustomResourceLoader', ['registerVehicle(', 'validateDataset(', 'lambda$reload$8(', 'lambda$reload$14(', 'public static void reload('], 'registration.javap.txt'),
                                         ('org.mtr.resource.ResourceManagerHelper', ['readAllResources(', 'readResource('], 'resource-resolution.javap.txt'),
                                         ('org.mtr.legacy.resource.CustomResourcesConverter', [' convert('], 'legacy-branch.javap.txt')]:
        result = subprocess.run([str(JAVAP), '-c', '-p', '-classpath', str(MTR), classname], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        (OUT / filename).write_text(methods(result.stdout, needles), encoding='utf-8')
    assessment['source_tools'] = {str(path): digest(path) for path in (pathlib.Path(__file__), ROOT.parent / 'tools/vehicle_catalog_map.py', ROOT.parent / 'tools/vehicle_formation_map.py', ROOT.parent / 'tools/legacy_vehicle_variants.py', ROOT.parent / 'tools/audit_vehicle_packs.py')}
    write('assessment.json', assessment)
    write('sha256.json', {path.name: digest(path) for path in sorted(OUT.iterdir()) if path.is_file() and path.name != 'sha256.json'})
    print(json.dumps({key: assessment[key] for key in ('expected_list_registration_count', 'expected_effective_registration_count', 'expected_distinct_id_strings', 'bbmodel_unique_resource_paths', 'bbmodel_referenced_by_effective_vehicles', 'static_vehicle_feature_counts')}) , flush=True)


if __name__ == '__main__':
    main()
