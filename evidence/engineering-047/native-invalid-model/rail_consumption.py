"""Save official default-rail consumer bytecode; no client execution."""

import json
import subprocess
import zipfile

from attribute import OUT, MTR, MTR_SHA, JAVAP, sha, byte_sha, write


CLASSES = ("org.mtr.render.RenderRails", "org.mtr.sound.VehicleSoundBase$RunSoundInfo",
           "org.mtr.resource.StoredModelResourceBase", "org.mtr.model.ModelLoaderBase",
           "org.mtr.model.BlockbenchModelLoader", "org.mtr.resource.BlockbenchModel",
           "org.mtr.legacy.resource.LegacyRailResource", "org.mtr.legacy.resource.LegacyObjectResource",
           "org.mtr.legacy.resource.LegacySignResource", "org.mtr.resource.ResourceManagerHelper")


def main():
    assert sha(MTR) == MTR_SHA
    inputs = []
    with zipfile.ZipFile(MTR) as archive:
        for classname in CLASSES:
            entry = classname.replace(".", "/") + ".class"
            raw = archive.read(entry)
            result = subprocess.run([str(JAVAP), "-J-Dfile.encoding=UTF-8", "-J-Dstdout.encoding=UTF-8",
                                     "-J-Dstderr.encoding=UTF-8", "-c", "-p", "-classpath", str(MTR), classname],
                                    capture_output=True, text=True, encoding="utf-8", errors="strict", check=True)
            filename = classname + ".javap.txt"
            (OUT / filename).write_text(result.stdout, encoding="utf-8")
            inputs.append({"archive_sha256": MTR_SHA, "entry": entry, "entry_sha256": byte_sha(raw), "javap": filename})
    write("rail-consumption-inputs.json", inputs)
    print(json.dumps({"classes_saved": len(inputs)}), flush=True)


if __name__ == "__main__":
    main()
