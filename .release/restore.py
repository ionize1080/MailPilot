from pathlib import Path
from zipfile import ZipFile
import gzip
import hashlib
import shutil
import subprocess

work = Path(".build/delivery")
old = work / "MailPilot-0.3.0-portable-win-x64.zip"
source = work / "Chatbox-1.20.3-MailPilot-source.zip"
portable = work / "MailPilot-0.3.1-portable-win-x64.zip"
def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

assert sha(old) == "31eb9474a5f28cde08647ac64abb3b733094e03fd33e733492c33218e22b4ab4"
assert sha(source) == "9079751b793d873a929b8fc8e4351db3b1431c6f3a6f8e4ec37319d675b0799a"
patch = work / "portable.patch"
patch.write_bytes(gzip.decompress(Path(".release/portable.patch.gz").read_bytes()))
old.rename(work / "MailPilot.zip")
subprocess.run(["git","apply","--binary","-p2","--directory=.build/delivery",str(patch)],check=True)
(work / "MailPilot.zip").rename(portable)
assert sha(portable) == "690065141a3f12f95be56cbd604a07893e0f97f204b21a5b72dbafdf010db9ee"
for file in (portable,source):
    with ZipFile(file) as archive:
        assert archive.testzip() is None
        if file == portable:
            assert len(archive.infolist()) == 5401
            archive.extractall(".build/portable-test")
out = Path(".build/verified")
out.mkdir()
checksums = "".join(f"{sha(file)}  {file.name}\n" for file in (portable,source))
(out/"SHA256SUMS.txt").write_bytes(checksums.encode("ascii"))
assert sha(out/"SHA256SUMS.txt")=="e9497cc75a0ccd89692407cb9b156b5147ce89721a5b27295c4040573439fcbe"
for file in (portable,source):
    shutil.move(file, out/file.name)
shutil.copyfile(".release/notes.md",out/"notes.md")
print(checksums)
