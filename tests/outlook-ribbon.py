"""Verify actual classic Outlook ribbon load and invoke its Settings callback."""
import ctypes
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
    if item.Connect and item.Object is None:
        item.Connect=False
    if not item.Connect:
        item.Connect=True
    for _ in range(80):
        pythoncom.PumpWaitingMessages()
        if item.Object is not None and item.Object.RibbonReady:
            break
        time.sleep(.1)
    assert item.Connect and item.Object.RibbonReady
    find=ctypes.windll.user32.FindWindowW
    find.restype=ctypes.c_void_p
    assert not find(None,"MailPilot · 设置"), "Close existing settings before running this test."
    item.Object.Settings(None)
    for _ in range(60):
        hwnd=find(None,"MailPilot · 设置")
        if hwnd:break
        time.sleep(.1)
    assert hwnd
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd),0x10,0,0)
    print("PASS Outlook",app.Version,"COM connection, onLoad and Settings callback")
finally:
    if owned:explorer.Close()
