"""Audit native directory migration consumers alongside the registry audit."""

import collections
import datetime
import json
import pathlib
import zipfile

from attribute import OUT, sha, byte_sha, load, write


def main():
    if (OUT / "legacy-directory-assessment.json").exists():
        raise ValueError("Refuse to overwrite completed directory evidence")
    reference = load((OUT / "assessment.json").read_bytes())
    entries, consumers = [], []
    for source in reference["sources"]:
        path = pathlib.Path(source["path"])
        assert sha(path) == source["sha256"]
        with zipfile.ZipFile(path) as archive:
            counts = collections.Counter(info.filename for info in archive.infolist())
            for info in archive.infolist():
                parts = info.filename.split("/")
                if info.is_dir() or len(parts) < 4 or parts[0] != "assets" or parts[2] not in ("rails", "eyecandies"):
                    continue
                assert counts[info.filename] == 1, "Ambiguous duplicate directory entry"
                eligible = parts[1] == "mtrsteamloco" and info.filename.endswith(".json")
                row = {"source_index": source["source_index"], "archive_sha256": source["sha256"],
                       "entry": info.filename, "bytes": info.file_size, "native_converter_eligible": eligible}
                if eligible:
                    raw = archive.read(info)
                    data = load(raw)
                    assert isinstance(data, dict)
                    row["entry_sha256"] = byte_sha(raw)
                    if "model" in data:
                        declarations = [(pathlib.PurePosixPath(info.filename).stem, "", data)]
                    else:
                        declarations = [(key, "/" + key.replace("~", "~0").replace("/", "~1"), value)
                                        for key, value in data.items()]
                    row["model_declaration_count"] = len(declarations)
                    for ordinal, (identifier, pointer, definition) in enumerate(declarations):
                        assert isinstance(definition, dict)
                        # Official map-entry conversion lowercases with Locale.ENGLISH; observed keys are ASCII.
                        assert identifier.isascii(), "Non-ASCII legacy IDs need an exact Java locale oracle"
                        native_identifier = identifier.lower() if pointer else identifier
                        # Every observed legacy model is an explicit string, so schema coercion/defaults are unnecessary.
                        model = definition["model"]
                        assert isinstance(model, str)
                        consumers.append({"source_index": source["source_index"], "archive_sha256": source["sha256"],
                                          "entry": info.filename, "entry_sha256": row["entry_sha256"],
                                          "json_pointer": pointer, "ordinal": ordinal, "id": native_identifier,
                                          "id_authored": identifier, "id_source": "map_key" if pointer else "filename_stem",
                                          "kind": "rail" if parts[2] == "rails" else "object", "model_authored": model,
                                          "native_model_resource": model, "texture_id_authored": definition.get("textureId"),
                                          "texture_id_field_present": "textureId" in definition,
                                          "supported_raw_case_sensitive_suffix": model.endswith((".bbmodel", ".obj"))})
                entries.append(row)
        print("Verified directory archive", source["source_index"], flush=True)
    invalid = [row for row in consumers if not row["supported_raw_case_sensitive_suffix"]]
    assessment = {"timestamp": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  "status": "static_directory_migration_audit_runtime_not_traced",
                  "source_reference": {"path": str(OUT / "assessment.json"), "sha256": sha(OUT / "assessment.json")},
                  "archives_reverified": len(reference["sources"]), "directory_entries_audited": len(entries),
                  "eligible_json_entries": sum(row["native_converter_eligible"] for row in entries),
                  "model_consumers_audited": len(consumers), "model_consumers_by_kind": dict(collections.Counter(row["kind"] for row in consumers)),
                  "unsupported_suffix_candidates": invalid,
                  "conversion": "Official convertRails/convertObjects use ResourceManagerHelper.readDirectory(rails/eyecandies), which enumerates listResourceStacks. Converter accepts namespace mtrsteamloco and case-sensitive .json suffix. A root model field selects a single declaration with an unchanged filename stem ID; otherwise map entry keys are lowercased with Locale.ENGLISH to become IDs. All observed keys are ASCII and authored IDs are preserved separately. LegacyRailResource/LegacyObjectResource copy model unchanged to native modelResource.",
                  "limits": ["Every observed eligible declaration explicitly provides a string model; no approximation of missing legacy schema defaults is used.",
                             "This audits all directory providers in the same 17 verified source archives, including superseded providers. It does not trace Minecraft resource stack order, registration winners, successful parsing, model rendering, or third-party archives outside this catalogue.",
                             "Supported suffix excludes this factory's unsupported-format branch; textureId absence is recorded without asserting decoded texture validity."],
                  "script_sha256": sha(pathlib.Path(__file__))}
    write("legacy-directory-entries.json", entries)
    write("legacy-directory-consumers.json", consumers)
    write("legacy-directory-assessment.json", assessment)
    print(json.dumps({key: assessment[key] for key in ("archives_reverified", "eligible_json_entries", "model_consumers_audited", "model_consumers_by_kind", "unsupported_suffix_candidates")}), flush=True)


if __name__ == "__main__":
    main()
