"""Ask the running classic Outlook add-in to host or release an Electron window."""
import sys
import json
import os
import time
import ctypes
import win32com.client

def follow(source):
    import win32gui, win32process, win32api
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
                try:
                    process = win32api.OpenProcess(0x1000, False, pid)
                    name = ctypes.create_unicode_buffer(32768)
                    size = ctypes.c_ulong(len(name))
                    ctypes.windll.kernel32.QueryFullProcessImageNameW(ctypes.c_void_p(int(process)),0,name,ctypes.byref(size))
                    pid_names[pid] = os.path.basename(name.value).lower()
                except Exception:
                    pid_names[pid] = ""
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
        outlook = win32com.client.GetActiveObject("Outlook.Application")
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
