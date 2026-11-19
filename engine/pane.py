"""Ask the running classic Outlook add-in to host or release an Electron window."""
import sys
import json
import os
import time
import ctypes
import pythoncom
import pywintypes
import win32com.client
import win32api
import win32gui
import win32process

def process_name(pid):
    try:
        process = win32api.OpenProcess(0x1000, False, pid)
        name = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(name))
        ctypes.windll.kernel32.QueryFullProcessImageNameW(ctypes.c_void_p(int(process)), 0, name, ctypes.byref(size))
        return os.path.basename(name.value).lower()
    except (OSError, pywintypes.error):
        return ""

def current_outlook():
    try:
        return win32com.client.GetActiveObject("Outlook.Application")
    except pythoncom.com_error as error:
        # A COM-started Explorer can be visible before Office lists it in the Running Object Table.
        hwnd = win32gui.FindWindow("rctrl_renwnd32", None)
        if error.hresult != -2147221021 or not hwnd or process_name(win32process.GetWindowThreadProcessId(hwnd)[1]) != "outlook.exe":
            raise
        return win32com.client.dynamic.Dispatch("Outlook.Application")

def follow(source):
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    target = "olk.exe" if source == "graph" else "outlook.exe"
    pid_names = {}
    previous = object()
    while True:
        windows = []
        def collect(h, _):
            if not win32gui.IsWindowVisible(h) or not win32gui.GetWindowText(h) or win32gui.GetWindow(h, 4):
                return
            pid = win32process.GetWindowThreadProcessId(h)[1]
            if pid not in pid_names:
                pid_names[pid] = process_name(pid)
            if pid_names[pid] == target:
                windows.append(h)
        win32gui.EnumWindows(collect, None)
        state = None
        if windows:
            h = windows[0]
            if win32gui.IsIconic(h):
                state = "minimized"
            else:
                l,t,r,b = win32gui.GetWindowRect(h)
                if r-l > 100 and b-t > 100:
                    state = {"bounds":dict(x=l,y=t,width=r-l,height=b-t), "active":h==win32gui.GetForegroundWindow()}
        if state != previous:
            print(json.dumps(state), flush=True)
            previous = state
        time.sleep(.3)

def main():
    action, tool, hwnd, side, width = sys.argv[1:]
    if tool not in ("search", "ai") or action not in ("attach", "detach", "hide", "icons"):
        return 2
    try:
        outlook = current_outlook()
        addin = outlook.COMAddIns.Item("MailPilot.Outlook")
        if not addin.Connect:
            return 1
        return 0 if addin.Object.SetPanel(action, tool, hwnd, side, int(width)) else 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1

if __name__ == "__main__":
    if len(sys.argv)==3 and sys.argv[1]=="follow":
        follow(sys.argv[2])
        sys.exit()
    sys.exit(main())
