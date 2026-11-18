"""Stage pinned redistributables. The target PC needs neither Python nor Node."""
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist/MailPilot"
CACHE = ROOT / ".build"
def prepare():
    lock = json.loads((ROOT / "scripts/runtime-lock.json").read_text())
    CACHE.mkdir(exist_ok=True)
    for name, spec in lock.items():
        p = CACHE / spec["url"].split("/")[-1]
        if not p.exists():
            urllib.request.urlretrieve(spec["url"], p)
        with p.open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != spec["sha256"]:
                raise ValueError("Hash mismatch: " + name)
        runtime = OUT / "Runtime"
        dest = OUT / "Browser" if name == "electron" else runtime
        if name in ("regex","pywin32"):
            dest = runtime / "Lib/site-packages"
        with zipfile.ZipFile(p) as archive:
            archive.extractall(dest)
    for dll in (runtime / "Lib/site-packages/pywin32_system32").glob("*.dll"):
        shutil.copy2(dll, runtime)
    (runtime / "python312._pth").write_text(
        "python312.zip\n.\n../engine\nLib/site-packages\nLib/site-packages/win32\nLib/site-packages/win32/lib\n", encoding="ascii")
    shutil.copytree(ROOT / "engine", OUT / "engine", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
if __name__ == "__main__":
    prepare()
