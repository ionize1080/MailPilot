"""Package only released components. Profile, index and test data stay outside the archive."""
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from runtime import ROOT,OUT

VERSION="0.2.1"

def stage_desktop():
    src, dest = ROOT/"desktop", OUT/"Desktop"
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("node_modules"))
    vendor = src/"node_modules/dompurify"
    required_version = json.loads((src/"package.json").read_text(encoding="utf-8"))["dependencies"]["dompurify"]
    installed = json.loads((vendor/"package.json").read_text(encoding="utf-8")) if (vendor/"package.json").is_file() else {}
    if installed.get("version") != required_version or not (vendor/"dist/purify.min.js").is_file():
        subprocess.run(["npm.cmd","ci","--ignore-scripts","--no-audit","--no-fund"], cwd=src, check=True)
    target = dest/"node_modules/dompurify"
    (target/"dist").mkdir(parents=True, exist_ok=True)
    for name in ("dist/purify.min.js","LICENSE","package.json"):
        shutil.copy2(vendor/name, target/name)
    shutil.copy2(ROOT/"chatbox/bootstrap.cjs",OUT/"Chatbox/bootstrap.cjs")
def dependencies():
    licenses=OUT/"licenses/npm"
    licenses.mkdir(parents=True,exist_ok=True)
    packages={}
    visited=set()
    def walk(modules):
        if not modules.is_dir() or modules.resolve() in visited:
            return
        visited.add(modules.resolve())
        for entry in modules.iterdir():
            if entry.name.startswith("."):
                continue
            group=entry.iterdir() if entry.name.startswith("@") else (entry,)
            for p in group:
                manifest=p/"package.json"
                if not manifest.is_file():
                    continue
                value=json.loads(manifest.read_text(encoding="utf-8-sig"))
                name=value.get("name","unknown")+"@"+value.get("version","unknown")
                if name not in packages:
                    ids=[]
                    for f in p.iterdir():
                        if f.is_file() and f.name.lower().split(".")[0] in ("license","licence","copying","notice","copyright"):
                            content=f.read_bytes()
                            key=hashlib.sha256(content).hexdigest()[:20]+".txt"
                            if not (licenses/key).exists(): (licenses/key).write_bytes(content)
                            ids.append(key)
                    packages[name]={"license":value.get("license",value.get("licenses","See package source")),"files":ids}
                walk(p/"node_modules")
    walk(ROOT/".build/chatbox/node_modules")
    walk(OUT/"Chatbox/node_modules")
    walk(OUT/"Desktop/node_modules")
    (licenses/"packages.json").write_text(json.dumps(packages,sort_keys=True,indent=2),encoding="utf-8")

def main():
    stage_desktop()
    required=("MailPilot.exe","MailPilot.Outlook.dll","Chatbox/dist/main/main.js","Chatbox/dist/preload/index.js",
              "Chatbox/dist/renderer/index.html","Chatbox/source-build.json","Browser/electron.exe","Runtime/python.exe",
              "Desktop/main.cjs","Desktop/search.html","Desktop/settings.html","Desktop/reader.html","Desktop/icons/mailpilot.ico")
    for path in required:
        if not (OUT/path).is_file():raise SystemExit("Missing: "+path)
    for n in ("README.md","LICENSE","THIRD-PARTY.md","TESTING.md","Enable.cmd","Disable.cmd"):
        shutil.copy2(ROOT/n,OUT/n)
    shutil.copytree(ROOT/"web",OUT/"web",dirs_exist_ok=True)
    shutil.copytree(ROOT/"engine",OUT/"engine",dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    dependencies()
    dest=OUT.parent
    portable=dest/("MailPilot-"+VERSION+"-portable-win-x64.zip")
    allow={"MailPilot.exe","MailPilot.Outlook.dll","Chatbox","Desktop","Browser","engine","Runtime","web","licenses",
           "README.md","LICENSE","THIRD-PARTY.md","TESTING.md","Enable.cmd","Disable.cmd"}
    with zipfile.ZipFile(portable,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in sorted(OUT.rglob("*")):
            rel=file.relative_to(OUT)
            if rel.parts[0] not in allow or not file.is_file():continue
            if "__pycache__" in rel.parts or file.suffix==".pyc":continue
            if file.suffix.lower() in {".pst",".ost",".sqlite3",".log",".db"} or "qwen-plan" in file.name.lower():
                raise ValueError("Unexpected local data in package: "+file.name)
            z.write(file,"MailPilot/"+rel.as_posix())
    source=dest/"Chatbox-1.20.3-MailPilot-source.zip"
    checkout=ROOT/".build/chatbox"
    names=subprocess.check_output(["git","-C",str(checkout),"ls-files","-z"]).decode().split("\0")
    with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in names:
            if name and (checkout/name).is_file():z.write(checkout/name,"chatbox-1.20.3/"+name)
        for name in ("bootstrap.cjs","package.json","package-lock.json"):
            z.write(ROOT/"chatbox"/name,"mailpilot-host/"+name)
        for name in ("preferences.cjs","window-layout.cjs"):
            z.write(ROOT/"desktop"/name,"Desktop/"+name)
        for name in ("preferences.json","pane.py"):
            z.write(ROOT/"engine"/name,"engine/"+name)
    hashes=[]
    for file in (portable,source):
        with file.open("rb") as f:digest=hashlib.file_digest(f,"sha256").hexdigest()
        hashes.append(digest+"  "+file.name)
    (dest/"SHA256SUMS.txt").write_text("\n".join(hashes)+"\n",encoding="ascii")
    print("\n".join(hashes))
if __name__=="__main__":
    main()
