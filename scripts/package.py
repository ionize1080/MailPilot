"""Package only released components. Profile, index and test data stay outside the archive."""
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from runtime import ROOT,OUT

VERSION="0.3.0"

def stage_desktop():
    src, dest = ROOT/"desktop", OUT/"Desktop"
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("node_modules"))
    modules = src/"node_modules"
    deps = json.loads((src/"package.json").read_text(encoding="utf-8"))["dependencies"]
    if any(not (modules/pkg/"package.json").is_file() or
           json.loads((modules/pkg/"package.json").read_text(encoding="utf-8"))["version"] != version
           for pkg, version in deps.items()):
        subprocess.run(["npm.cmd","ci","--ignore-scripts","--omit=optional","--no-audit","--no-fund"], cwd=src, check=True)
    runtime = {"dompurify":["dist/purify.min.js"], "marked":["lib/marked.esm.js"],
               "office-oxide-wasm":["web/office_oxide.js","web/office_oxide_bg.wasm","LICENSE-MIT","LICENSE-APACHE"],
               "@silurus/ooxml":["dist"], "@silurus/ooxml-legacy-office":["dist"],
               "pdfjs-dist":["build/pdf.min.mjs","build/pdf.worker.min.mjs","build/pdf.renderer.min.mjs",
                             "cmaps","standard_fonts","iccs","wasm"]}
    for pkg, assets in runtime.items():
        vendor, target = modules/pkg, dest/"node_modules"/pkg
        for name in assets + ["package.json", "LICENSE", "LICENSE.md", "THIRD_PARTY_NOTICES.md"]:
            source = vendor/name
            if source.is_dir():
                shutil.copytree(source, target/name, dirs_exist_ok=True, ignore=shutil.ignore_patterns("types","*.map"))
            elif source.is_file():
                (target/name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target/name)
    # Browsers and module workers resolve the legacy reader's peer import without a bundler.
    for module in (dest/"node_modules/@silurus/ooxml-legacy-office/dist").glob("legacy-source-*.js"):
        code = module.read_text(encoding="utf-8").replace('"@silurus/ooxml/internal/companion"', '"../../ooxml/dist/internal-companion.mjs"')
        module.write_text(code, encoding="utf-8")
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
              "Desktop/main.cjs","Desktop/search.html","Desktop/settings.html","Desktop/reader.html","Desktop/icons/mailpilot.ico",
              "Desktop/viewer.html","Desktop/attachment-host.cjs","Desktop/node_modules/@silurus/ooxml/dist/docx_parser_bg.wasm",
              "Desktop/node_modules/pdfjs-dist/build/pdf.worker.min.mjs")
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
