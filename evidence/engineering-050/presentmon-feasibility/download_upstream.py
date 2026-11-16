"""Download one official released console asset without installing it."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import urllib.parse

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OUT = BASE / "upstream-download-01"
CACHE = ROOT / ".cache/acceptance/presentmon-upstream-050"
API = "https://api.github.com/repos/GameTechDev/PresentMon/releases/tags/v2.6.0"


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def download(url, destination):
    receipt = {"url": url, "started": now()}
    request = urllib.request.Request(url, headers={"User-Agent": "MTR-Memory-Saver-owned-feasibility", "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*"})
    with urllib.request.urlopen(request, timeout=45) as response:
        receipt.update(status=response.status, headers={name: response.headers.get(name) for name in
            ("Content-Type", "Content-Length", "ETag", "Last-Modified")})
        final = urllib.parse.urlsplit(response.url)
        receipt["final_url_without_temporary_query"] = urllib.parse.urlunsplit((final.scheme, final.netloc, final.path, "", ""))
        with destination.open("xb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
                if stream.tell() > 10 * 1024 * 1024:
                    raise ValueError("Unexpectedly large console asset/metadata")
    receipt.update(ended=now(), bytes=destination.stat().st_size, sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    return receipt


OUT.mkdir(parents=True, exist_ok=False)
CACHE.mkdir(parents=True, exist_ok=False)
result = {"started": now(), "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "command": [sys.executable, str(Path(__file__))], "passed": False, "downloads": []}
try:
    result["downloads"].append(download(API, OUT / "release-api.json"))
    release = json.loads((OUT / "release-api.json").read_text(encoding="utf-8"))
    assert release["tag_name"] == "v2.6.0" and not release["draft"] and not release["prerelease"]
    assert release["html_url"] == "https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0"
    assets = [asset for asset in release["assets"] if asset["name"].lower().endswith("-x64.exe") and "presentmon" in asset["name"].lower()]
    assert len(assets) == 1, "Require one exact released x64 console executable"
    asset, = assets
    assert Path(asset["name"]).name == asset["name"]
    assert asset["browser_download_url"].startswith("https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/")
    path = CACHE / asset["name"]
    result["downloads"].append(download(asset["browser_download_url"], path))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_size == asset["size"]
    assert asset.get("digest") == "sha256:" + digest, "Official GitHub asset SHA-256 does not match downloaded bytes"
    result["downloads"].append(download("https://raw.githubusercontent.com/GameTechDev/PresentMon/v2.6.0/LICENSE.txt", OUT / "LICENSE.txt"))
    result.update(passed=True, release=release["html_url"], release_tag=release["tag_name"],
                  asset_id=asset["id"], official_asset_digest=asset["digest"], executable=str(path.resolve()),
                  sha256=digest, installed=False, existing_frameview_overwritten=False)
finally:
    result["ended"] = now()
    write(OUT / "download.execution.json", result)
print(json.dumps({key: result[key] for key in ("passed", "executable", "sha256", "release")}))
