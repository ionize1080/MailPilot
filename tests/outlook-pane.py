"""Exercise both docked Electron tools against the installed classic Outlook add-in."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import pythoncom
from win32com.client import dynamic

root = Path(__file__).resolve().parents[1]

def run():
    app = dynamic.Dispatch("Outlook.Application")
    ns = app.GetNamespace("MAPI")
    with tempfile.TemporaryDirectory(dir=root/".build", ignore_cleanup_errors=True) as tmp:
        pst = str(Path(tmp)/"panes.pst")
        ns.AddStoreEx(pst, 3)
        store = next(s for s in ns.Stores if s.FilePath.casefold()==pst.casefold())
        folder = store.GetRootFolder()
        explorer = folder.Folders.Add("MailPilot panel QA", 6).GetExplorer(0)
        explorer.Display()
        try:
            addin = app.COMAddIns.Item("MailPilot.Outlook")
            assert addin.Connect and addin.Object is not None, "Enable the test bundle first"
            for extra in ([], ["-Assistant"]):
                child = subprocess.Popen(["pwsh","-NoProfile","-File",str(root/"tests/desktop-ui.ps1"),*extra],
                                         env=os.environ | {"MAILPILOT_EXPECT_PANE":"1"})
                while child.poll() is None:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(.1)
                assert child.returncode == 0, "Outlook pane validation failed"
        finally:
            ns.RemoveStore(folder)
            try:
                explorer.Close()
            except Exception:
                pass  # Removing this explorer's store can close it as well.

if __name__=="__main__":
    run()
