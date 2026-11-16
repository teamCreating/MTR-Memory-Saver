"""Read-only official 4.1.0-beta.2 attribution; writes only this evidence folder.

No client launch, instrumentation, reload, archive edit, or runtime-source claim.
"""

import collections
import contextlib
import datetime
import hashlib
import json
import pathlib
import struct
import subprocess
import warnings
import zipfile


OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PLAN = ROOT / "evidence/engineering-046/full-load-initial-nf248/packaged-client-plan.json"
CATALOG = ROOT.parent / "[MTR4.1原生目录]产物/catalog.json"
MTR_SHA = "ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa"
MTR = ROOT / f".cache/dependencies/mtr-{MTR_SHA}.jar"
JAVAP = pathlib.Path("C:/Users/ben_l/Saved Games/Yuuniverse 1.20.1 Shenyang/porting-output/work/tools/jdk21/jdk-21.0.11+10/bin/javap.exe")
REGISTRIES = ("assets/mtr/mtr_custom_resources.json", "assets/mtr/mtr_custom_resources_pending_migration.json")
MODEL_LISTS = ("models", "bogie1Models", "bogie2Models")
TRANSPARENT_ENTRY = "assets/mtr/textures/block/transparent.png"
CLASSES = (
    "org.mtr.client.CustomResourceLoader",
    "org.mtr.resource.RailResource",
    "org.mtr.generated.resource.RailResourceSchema",
    "org.mtr.resource.ObjectResource",
    "org.mtr.generated.resource.ObjectResourceSchema",
    "org.mtr.resource.VehicleModel",
    "org.mtr.generated.resource.VehicleModelSchema",
    "org.mtr.resource.CustomResourceTools",
    "org.mtr.resource.LiftResource",
    "org.mtr.resource.SignResource",
    "org.mtr.legacy.resource.CustomResourcesConverter",
    "org.mtr.core.serializer.JsonReader",
    "org.mtr.core.serializer.ReaderBase",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def byte_sha(value):
    return hashlib.sha256(value).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate authored JSON key: " + key)
        result[key] = value
    return result


def load(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)


def constant_pool(raw):
    """Decode constant-pool method references; not runtime or instruction tracing."""
    assert raw[:4] == b"\xca\xfe\xba\xbe"
    count = struct.unpack_from(">H", raw, 8)[0]
    cp = [None] * count
    offset, index = 10, 1
    while index < count:
        tag = raw[offset]
        offset += 1
        if tag == 1:
            length = struct.unpack_from(">H", raw, offset)[0]
            offset += 2
            cp[index] = (tag, raw[offset:offset + length].decode("utf-8", errors="replace"))
            offset += length
        elif tag in (3, 4):
            cp[index] = (tag,)
            offset += 4
        elif tag in (5, 6):
            cp[index] = (tag,)
            offset += 8
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            cp[index] = (tag, struct.unpack_from(">H", raw, offset)[0])
            offset += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            cp[index] = (tag, *struct.unpack_from(">HH", raw, offset))
            offset += 4
        elif tag == 15:
            cp[index] = (tag, *struct.unpack_from(">BH", raw, offset))
            offset += 3
        else:
            raise ValueError("Unsupported constant-pool tag " + str(tag))
        index += 1
    strings = [item[1] for item in cp if item and item[0] == 1]
    methods = []
    for index, item in enumerate(cp):
        if item and item[0] in (10, 11):
            owner = cp[cp[item[1]][1]][1]
            name_type = cp[item[2]]
            methods.append({"constant_pool_index": index, "owner": owner,
                            "name": cp[name_type[1]][1], "descriptor": cp[name_type[2]][1]})
    return strings, methods


def find_line(text, needle):
    matches = [index for index, line in enumerate(text.splitlines(), 1) if needle in line]
    assert matches, needle
    return matches


def main():
    if (OUT / "assessment.json").exists():
        raise ValueError("Refuse to overwrite completed attribution evidence")
    plan = load(PLAN.read_bytes())
    catalog = load(CATALOG.read_bytes())
    assert plan["artifact"]["target"] == "official-nf248"
    assert plan["artifact"]["mtrSha256"] == MTR_SHA
    assert len(plan["packs"]) == len(catalog["packs"]) == 16
    assert catalog["passed"] is True
    sources = [{"source_index": 0, "kind": "official_mtr", "path": str(MTR), "filename": MTR.name,
                "expected_sha256": MTR_SHA, "sha256": sha(MTR)}]
    for index, (prepared, pack) in enumerate(zip(plan["packs"], catalog["packs"]), 1):
        path = pathlib.Path(prepared["source"])
        assert path.resolve() == (CATALOG.parent / pack["output"]).resolve()
        actual = sha(path)
        assert actual == prepared["sha256"] == pack["output_sha256"]
        sources.append({"source_index": index, "kind": "catalogue_pack", "path": str(path),
                        "filename": path.name, "expected_sha256": prepared["sha256"], "sha256": actual})
        print("Verified archive", index, flush=True)
    assert sources[0]["sha256"] == MTR_SHA
    bytecodes, class_inputs, cp_findings = {}, [], []
    scanned = 0
    class_scan_warnings = []
    model_rows, registry_rows, skipped_legacy, empty_lists = [], [], [], []
    texture_origins = []
    declaration_counts = collections.Counter()
    field_counts = collections.Counter()
    with contextlib.ExitStack() as stack:
        archives = [stack.enter_context(zipfile.ZipFile(source["path"])) for source in sources]
        official = archives[0]
        for classname in CLASSES:
            entry = classname.replace(".", "/") + ".class"
            raw = official.read(entry)
            result = subprocess.run([str(JAVAP), "-J-Dfile.encoding=UTF-8", "-J-Dstdout.encoding=UTF-8",
                                     "-J-Dstderr.encoding=UTF-8", "-c", "-p", "-classpath", str(MTR), classname],
                                    capture_output=True, text=True, encoding="utf-8", errors="strict", check=True)
            filename = classname + ".javap.txt"
            (OUT / filename).write_text(result.stdout, encoding="utf-8")
            bytecodes[classname] = result.stdout
            class_inputs.append({"source_index": 0, "archive_sha256": MTR_SHA, "entry": entry,
                                 "entry_sha256": byte_sha(raw), "bytes": len(raw), "javap": filename})
        for info in official.infolist():
            if not info.is_dir() and info.filename.endswith(".class"):
                scanned += 1
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter("always")
                    raw = official.read(info)
                class_scan_warnings.extend({"entry": info.filename, "category": warning.category.__name__,
                                            "message": str(warning.message)} for warning in captured)
                strings, methods = constant_pool(raw)
                relevant = [method for method in methods
                            if (method["owner"] == "org/mtr/resource/VehicleModel" and method["name"] == "getModelLoaderBase")
                            or (method["owner"] == "org/mtr/resource/RailResource" and method["name"] == "<init>"
                                and method["descriptor"] == "(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;)V")]
                literal = "[{}] Invalid model!" in strings
                if relevant or literal:
                    cp_findings.append({"entry": info.filename, "entry_sha256": byte_sha(raw),
                                        "method_references": relevant, "contains_invalid_model_log_literal": literal})
        for source_index, archive in enumerate(archives):
            candidates = [info for info in archive.infolist() if info.filename == TRANSPARENT_ENTRY]
            assert len(candidates) <= 1, (source_index, TRANSPARENT_ENTRY)
            if candidates:
                raw = archive.read(candidates[0])
                texture_origins.append({"source_index": source_index, "archive_sha256": sources[source_index]["sha256"],
                                        "entry": TRANSPARENT_ENTRY, "entry_sha256": byte_sha(raw), "bytes": len(raw),
                                        "png_magic_matches": raw[:8] == b"\x89PNG\r\n\x1a\n",
                                        "decoded_or_validated": False})
        for registry in REGISTRIES:
            for source_index, archive in enumerate(archives):
                matches = [info for info in archive.infolist() if info.filename == registry]
                assert len(matches) <= 1, (source_index, registry)
                if not matches:
                    registry_rows.append({"source_index": source_index, "entry": registry, "present": False})
                    continue
                raw = archive.read(matches[0])
                data = load(raw)
                assert isinstance(data, dict)
                legacy = "custom_trains" in data or "custom_signs" in data
                base = {"source_index": source_index, "archive_sha256": sources[source_index]["sha256"],
                        "entry": registry, "entry_sha256": byte_sha(raw), "present": True,
                        "bytes": len(raw), "keys": list(data), "legacy_branch": legacy}
                counts = {kind: len(data.get(kind, [])) for kind in ("vehicles", "rails", "objects", "lifts")}
                registry_rows.append({**base, "declaration_counts": counts,
                                      "legacy_train_count": len(data.get("custom_trains", {})),
                                      "legacy_sign_count": len(data.get("custom_signs", {}))})
                if legacy:
                    assert not data.get("custom_trains"), "Legacy vehicle conversion needs separate attribution"
                    assert not any(counts.values()), "Mixed native/legacy branch needs separate attribution"
                    skipped_legacy.append({**base, "legacy_train_count": len(data.get("custom_trains", {})),
                                           "legacy_sign_count": len(data.get("custom_signs", {}))})
                    continue
                for kind in ("vehicles", "rails", "objects"):
                    rows = data.get(kind, [])
                    assert isinstance(rows, list)
                    declaration_counts[kind] += len(rows)
                    for ordinal, definition in enumerate(rows):
                        assert isinstance(definition, dict)
                        if kind == "vehicles":
                            lists = [(field, definition.get(field, [])) for field in MODEL_LISTS]
                        else:
                            lists = [(None, [definition])]
                        for field, models in lists:
                            assert isinstance(models, list)
                            if not models:
                                empty_lists.append({"source_index": source_index, "entry": registry, "kind": kind,
                                                    "id": definition.get("id"), "ordinal": ordinal, "field": field})
                            for model_ordinal, model in enumerate(models):
                                assert isinstance(model, dict)
                                model_value = model.get("modelResource", "")
                                texture_value = model.get("textureResource", "")
                                # All observed values must be strings; no coercion approximates JsonReader here.
                                assert isinstance(model_value, str) and isinstance(texture_value, str)
                                supported = model_value.endswith((".bbmodel", ".obj"))
                                pointer = f"/{kind}/{ordinal}" + (f"/{field}/{model_ordinal}" if field else "")
                                field_counts[kind + ("." + field if field else "")] += 1
                                model_rows.append({"source_index": source_index, "archive_sha256": sources[source_index]["sha256"],
                                                   "entry": registry, "entry_sha256": base["entry_sha256"],
                                                   "json_pointer": pointer, "kind": kind, "id": definition.get("id"),
                                                   "transport_mode": definition.get("transportMode") if kind == "vehicles" else None,
                                                   "definition_ordinal": ordinal, "model_list": field,
                                                   "model_ordinal": model_ordinal if field else None,
                                                   "model_resource_authored": model.get("modelResource"),
                                                   "model_resource_field_present": "modelResource" in model,
                                                   "model_resource_with_schema_default": model_value,
                                                   "texture_resource_authored": model.get("textureResource"),
                                                   "texture_resource_field_present": "textureResource" in model,
                                                   "texture_resource_with_schema_default": texture_value,
                                                   "supported_raw_case_sensitive_suffix": supported,
                                                   "empty_texture_with_schema_default": texture_value == ""})
    native = bytecodes["org.mtr.client.CustomResourceLoader"]
    rail = bytecodes["org.mtr.resource.RailResource"]
    vehicle = bytecodes["org.mtr.resource.VehicleModel"]
    tools = bytecodes["org.mtr.resource.CustomResourceTools"]
    assert "123: ldc" in native and "// String default" in native
    assert "125: ldc" in native and "// String Default" in native
    assert '132: invokespecial' in native and 'RailResource."<init>":(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;)V' in native
    empty_constants = [line.strip() for line in rail.splitlines() if line.rstrip().endswith("// String")]
    assert any(line.startswith("5: ldc") for line in empty_constants)
    assert any(line.startswith("7: ldc") for line in empty_constants)
    assert "36: invokestatic" in rail and "VehicleModel.getModelLoaderBase" in rail
    assert "111: ldc" in vehicle and "// String [{}] Invalid model!" in vehicle
    assert "113: aload         4" in vehicle and "1: ldc" in vehicle and "// String png" in vehicle
    assert "// String textures/block/transparent.png" in tools
    invalid = [row for row in model_rows if not row["supported_raw_case_sensitive_suffix"]]
    logs = []
    for relative in ("evidence/engineering-046/full-load-initial-nf248/latest.log",
                     "evidence/engineering-046/packaged-faults-nf248/latest.log",
                     "evidence/engineering-046/packaged-faults-nf265/latest.log"):
        path = ROOT / relative
        raw = path.read_bytes()
        lines = raw.decode("utf-8-sig").splitlines()
        logs.append({"path": str(path), "sha256": byte_sha(raw),
                     "occurrences": [{"line": index, "text": line} for index, line in enumerate(lines, 1)
                                     if "Invalid model!" in line],
                     "runtime_caller_traced": False})
    evidence_lines = {
        "reload_default_rail": {"file": "org.mtr.client.CustomResourceLoader.javap.txt",
                                "lines": find_line(native, "119: new") + find_line(native, "// String default") + find_line(native, "// String Default") + find_line(native, "132: invokespecial")},
        "rail_convenience_constructor": {"file": "org.mtr.resource.RailResource.javap.txt",
                                         "lines": find_line(rail, "RailResource(java.lang.String, java.lang.String") + find_line(rail, "36: invokestatic")},
        "invalid_branch": {"file": "org.mtr.resource.VehicleModel.javap.txt",
                           "lines": find_line(vehicle, "getModelLoaderBase(java.lang.String") + find_line(vehicle, "// String [{}] Invalid model!")},
        "default_texture": {"file": "org.mtr.resource.CustomResourceTools.javap.txt",
                            "lines": find_line(tools, "formatIdentifierWithDefault(java.lang.String") + find_line(tools, "// String textures/block/transparent.png")},
    }
    generated_source = {"source_index": 0, "archive": str(MTR), "archive_sha256": MTR_SHA,
                        "entry": "org/mtr/client/CustomResourceLoader.class", "registry_entry": None, "json_pointer": None,
                        "id": "default", "name": "Default", "model_resource": "", "texture_resource": "",
                        "caller": "org.mtr.client.CustomResourceLoader.reload()", "caller_bytecode_offset": 132,
                        "constructor": "org.mtr.resource.RailResource(String,String,ResourceProvider)",
                        "model_factory_bytecode_offset": 36, "expected_log_texture": "mtr:textures/block/transparent.png",
                        "should_preload": False, "origin": "Programmatic native registration before registry read",
                        "runtime_caller_traced": False}
    assessment = {
        "timestamp": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "status": "official_generated_source_proven_statically_runtime_caller_not_traced",
        "target": "official MTR 4.1.0-beta.2", "v6_validation_performed": False,
        "source_plan": {"path": str(PLAN), "sha256": sha(PLAN)},
        "catalogue": {"path": str(CATALOG), "sha256": sha(CATALOG)},
        "verified_source_archives": len(sources), "catalogue_pack_archives": len(sources) - 1,
        "sources": sources, "class_inputs": class_inputs, "official_classes_scanned": scanned,
        "constant_pool_findings": cp_findings, "constant_pool_limit": "Method references/literals establish static candidates; actual invocations checked in saved javap, not runtime tracing.",
        "official_class_scan_warnings": class_scan_warnings,
        "native_generated_source": generated_source, "bytecode_evidence_lines": evidence_lines,
        "registry_slots_checked": len(registry_rows), "registry_entries_present": sum(row["present"] for row in registry_rows),
        "native_declarations_audited": dict(declaration_counts), "model_fields_audited": dict(field_counts),
        "model_consumer_rows_audited": len(model_rows), "unsupported_suffix_authored_candidates": len(invalid),
        "unsupported_suffix_authored_candidates_with_empty_texture": sum(row["empty_texture_with_schema_default"] for row in invalid),
        "empty_model_lists": len(empty_lists), "legacy_branches_without_trains_skipped": skipped_legacy,
        "legacy_sign_declarations_excluded_from_model_consumer_audit": sum(row["legacy_sign_count"] for row in skipped_legacy),
        "transparent_texture_origins": texture_origins, "archived_logs": logs,
        "findings": [
            "Official reload programmatically registers rail id default / name Default before reading either registry. Its convenience constructor supplies empty modelResource and empty textureResource, then unconditionally calls VehicleModel.getModelLoaderBase.",
            "Factory formats textureResource first, tests raw modelResource suffix case-sensitively for .bbmodel/.obj, and logs the formatted texture identifier on unsupported-model fallback. Empty modelResource therefore prints the transparent default. This line is not an assertion that the PNG bytes are an invalid model.",
            "Audit includes every native model consumer declaration in both registries across the verified official archive and 16 catalogue archives, including superseded declarations. All observed model/texture fields are strings or absent; missing fields use the verified empty schema default. Nonempty legacy vehicle conversion, mixed legacy/native arrays, or duplicate JSON keys would stop the audit.",
            "Two legacy registry branches contain no custom_trains; one contains seven custom_signs. Saved converter/SignResource bytecode and the full class reference scan separate sign conversion from VehicleModel.getModelLoaderBase consumers. These signs are recorded but excluded from the model consumer count.",
            "LiftResource is saved for boundary review and does not reference getModelLoaderBase. Its default_transparent lift is not assigned as this source merely because its modelResource is absent.",
        ],
        "limits": [
            "No new game run, runtime call-stack trace, mod-free baseline, or resource reload was performed. Archived logs still involve the companion/product setup recorded in their original plans.",
            "Static native call chain proves a built-in source capable of producing this exact line per successful reload reach. It does not trace the individual archived or active log occurrence, establish absence of third-party code invocations, or prove the resulting fallback has no render/behavior/performance impact.",
            "Asset suffix audit excludes this particular unsupported-format branch for audited authored consumers; it does not prove referenced model parsing, textures, geometry, properties, or runtime provider selection are valid.",
            "PNG magic is metadata only. No PNG decode or integrity conclusion is made or needed for this log attribution.",
        ],
        "tools": {"script": str(pathlib.Path(__file__)), "script_sha256": sha(pathlib.Path(__file__)),
                  "javap": str(JAVAP), "javap_sha256": sha(JAVAP),
                  "javap_jvm_encoding_options": ["-J-Dfile.encoding=UTF-8", "-J-Dstdout.encoding=UTF-8", "-J-Dstderr.encoding=UTF-8"]},
    }
    write("registry-audit.json", registry_rows)
    write("model-consumers.json", model_rows)
    write("unsupported-model-candidates.json", invalid)
    write("empty-model-lists.json", empty_lists)
    write("assessment.json", assessment)
    write("sha256.json", {path.name: sha(path) for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "sha256.json"})
    print(json.dumps({key: assessment[key] for key in ("verified_source_archives", "official_classes_scanned", "native_declarations_audited", "model_consumer_rows_audited", "unsupported_suffix_authored_candidates", "registry_entries_present")}), flush=True)


if __name__ == "__main__":
    main()
