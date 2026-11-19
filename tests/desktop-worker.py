"""Run the released UI worker against fixture originals and a private Windows clipboard."""
import contextlib
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import win32clipboard
import attachments
import graph
import outlook
from service import Session

home = Path(os.environ["MAILPILOT_HOME"]).resolve()
assert home.parent.name == ".build" and home.name.startswith("desktop-qa-")
user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.CreateWindowStationW.restype = ctypes.c_void_p
station = user32.CreateWindowStationW(None, 0, 0x02000000, None)
assert station and user32.SetProcessWindowStation(ctypes.c_void_p(station)), ctypes.get_last_error()
def fixture_reader(row):
    assert row['store'] == 'qa'
    def fetch(index, file, dest):
        source = home/'originals'/file['name']
        assert source.parent == home/'originals'
        shutil.copyfile(source,dest)
    return fetch
outlook.attachment_reader = lambda row, meta: contextlib.nullcontext(fixture_reader(row))
graph.attachment_reader = lambda cfg, row, cancel: fixture_reader(row)
copy_files = attachments.copy_files
def verify_copy(paths):
    copy_files(paths)
    win32clipboard.OpenClipboard()
    try:
        actual = [Path(p) for p in win32clipboard.GetClipboardData(15)]
        assert actual == paths
        (home/'clipboard.json').write_text(json.dumps([str(p) for p in actual]),encoding='utf-8')
    finally:
        win32clipboard.CloseClipboard()
attachments.copy_files = verify_copy
sys.stdin.reconfigure(encoding='utf-8-sig')
sys.stdout.reconfigure(encoding='utf-8')
Session(False).run()
