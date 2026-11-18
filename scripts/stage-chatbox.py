import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from runtime import ROOT, OUT
src=ROOT/".build/chatbox"
dest=OUT/"Chatbox"
dest.mkdir(parents=True,exist_ok=True)
for name in ("package.json","package-lock.json","bootstrap.cjs"):
    shutil.copy2(ROOT/"chatbox"/name,dest/name)
subprocess.run(["npm.cmd","ci","--ignore-scripts","--omit=dev","--no-audit","--no-fund"],cwd=dest,check=True)
built=src/"release/app/dist"
if not (built/"renderer/index.html").exists():
    raise SystemExit("Compile the Chatbox renderer first.")
if (dest/"dist").exists():
    target=(dest/"dist").resolve()
    assert target.parent==dest.resolve() and target.name=="dist"
    shutil.rmtree(target)
shutil.copytree(built,dest/"dist",ignore=shutil.ignore_patterns("*.map","stats.html"))
shutil.copytree(src/"assets",dest/"resources/assets",dirs_exist_ok=True)
shutil.copy2(src/"LICENSE",dest/"LICENSE")
files={str(p.relative_to(dest)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in sorted((dest/"dist").rglob("*")) if p.is_file()}
(dest/"source-build.json").write_text(json.dumps({"upstream":"https://github.com/chatboxai/chatbox","version":"1.20.3",
    "commit":subprocess.check_output(["git","-C",str(src),"rev-parse","HEAD"],text=True).strip(),
    "build":"electron-vite build","files":files},indent=2),encoding="utf-8")
