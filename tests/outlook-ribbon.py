"""Verify actual classic Outlook ribbon load and invoke its Settings callback."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import time
import pythoncom
from win32com.client import dynamic

app=dynamic.Dispatch("Outlook.Application")
explorer=app.ActiveExplorer()
owned=explorer is None
if owned:
    explorer=app.Session.GetDefaultFolder(6).GetExplorer(0)
    explorer.Display()
try:
    item=app.COMAddIns.Item("MailPilot.Outlook")
    for _ in range(80):
        pythoncom.PumpWaitingMessages()
        if item.Connect and item.Object is not None and item.Object.RibbonReady:
            break
        time.sleep(.1)
    assert item.Connect, "MailPilot did not connect at Outlook startup."
    assert item.Object is not None and item.Object.RibbonReady, "Missing Outlook ribbon onLoad."
    exe=Path(item.Object.LoadedPath).with_name("MailPilot.exe")
    with tempfile.TemporaryDirectory() as tmp:
        report=Path(tmp)/"outlook.txt"
        subprocess.run([str(exe),"diagnose",str(report)],check=True,timeout=20)
        assert "已验证" in report.read_text(encoding="utf-8-sig").splitlines()[0]
    find=ctypes.windll.user32.FindWindowW
    find.restype=ctypes.c_void_p
    assert not find(None,"MailPilot · 设置"), "Close existing settings before running this test."
    item.Object.Settings(None)
    for _ in range(60):
        hwnd=find(None,"MailPilot · 设置")
        if hwnd and ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            break
        time.sleep(.1)
    else:
        raise AssertionError("The Outlook Settings button did not show a window.")
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd),0x10,0,0)
    for _ in range(40):
        if not ctypes.windll.user32.IsWindow(ctypes.c_void_p(hwnd)):
            break
        time.sleep(.1)
    print("PASS Outlook",app.Version,"COM connection, onLoad and Settings callback")
finally:
    if owned:explorer.Close()
