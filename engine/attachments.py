"""Retrieve original attachment bytes only when the user requests a file."""
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import time

from config import HOME
from indexdb import mail_key

def filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ") or "附件"
    if re.match(r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³])(?:\s*\.|$)", name, re.I):
        name = "_" + name
    if len(name.encode("utf-16-le")) <= 480:
        return name
    suffix = Path(name).suffix[:24]
    stem = Path(name).stem.encode("utf-16-le")[:480-len(suffix.encode("utf-16-le"))]
    return stem.decode("utf-16-le", errors="ignore") + suffix

def manifest(db, args):
    row = db.execute("SELECT store,entry,stamp,attachments,metadata FROM mail WHERE id=?", (args["id"],)).fetchone()
    if not row or args["key"] != mail_key(row["store"], row["entry"]) or args["stamp"] != row["stamp"]:
        raise ValueError("这封邮件已更改，请重新选择查找结果。")
    metadata = json.loads(row["metadata"])
    files = metadata.get("files", [])
    files = [(files[i] if i < len(files) else {}) | {"name": name}
             for i, name in enumerate(json.loads(row["attachments"]))]
    return dict(row), metadata, files

def move_unique(temp, folder, name):
    safe = filename(name)
    stem, ext = os.path.splitext(safe)
    number = 1
    while True:
        path = folder / (safe if number == 1 else f"{stem} ({number}){ext}")
        try:
            os.rename(temp, path)  # On Windows this never replaces an existing destination.
            return path
        except FileExistsError:
            number += 1

def copy_files(paths):
    import win32clipboard
    import pywintypes
    data = struct.pack("<IiiII", 20, 0, 0, 0, 1) + ("\0".join(map(str, paths)) + "\0\0").encode("utf-16le")
    for attempt in range(10):
        try:
            win32clipboard.OpenClipboard()
            break
        except pywintypes.error:
            if attempt == 9:
                raise ValueError("剪贴板正被其他程序使用，请重试。") from None
            time.sleep(.035)
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(15, data)  # CF_HDROP
    finally:
        win32clipboard.CloseClipboard()

def transfer(row, metadata, files, cfg, args, cancel=lambda: False):
    mode, index = args["action"], args.get("index")
    if mode not in ("save", "copy", "preview") or (index is not None and
            (type(index) is not int or not 0 <= index < len(files))) or (mode == "preview" and index is None):
        raise ValueError("无效的附件操作。")
    indices = range(len(files)) if index is None else (index,)
    if not files:
        raise ValueError("邮件没有附件。")
    if mode == "copy":
        cache = HOME / "AttachmentClipboard"
        cache.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="copy-", dir=cache))
    else:
        target = Path(args["destination"])
        folder = target if index is None else target.parent
    paths, errors = [], []
    try:
        if cfg["source"] == "graph":
            from graph import attachment_reader
            reader = contextlib.nullcontext(attachment_reader(cfg, row, cancel))
        else:
            from outlook import attachment_reader
            reader = attachment_reader(row, metadata)
        with reader as fetch:
            for i in indices:
                file = files[i]
                fd, tmp = tempfile.mkstemp(prefix=".mailpilot-", suffix=".tmp", dir=folder)
                os.close(fd)
                temp = Path(tmp)
                try:
                    fetch(i, file, temp)
                    if cancel():
                        raise InterruptedError("已切换附件")
                    if mode != "preview":
                        try:
                            Path(str(temp) + ":Zone.Identifier").write_bytes(b"[ZoneTransfer]\r\nZoneId=3\r\n")
                        except OSError:
                            pass  # Some removable volumes do not support NTFS streams.
                    if mode == "copy" or index is None:
                        paths.append(move_unique(temp, folder, file["name"]))
                    else:
                        os.replace(temp, target)
                        paths.append(target)
                except Exception as error:
                    if index is not None:
                        raise
                    errors.append(file["name"] + "：" + str(error))
                finally:
                    temp.unlink(missing_ok=True)
        if mode == "copy":
            if paths:
                copy_files(paths)
            else:
                raise ValueError("没有可复制的附件。" + "；".join(errors))
    except Exception:
        if mode == "copy":
            shutil.rmtree(folder, ignore_errors=True)
        raise
    if mode == "copy":
        # Explorer may paste after MailPilot exits. Retire past batches only after replacing the clipboard.
        for old in cache.glob("copy-*"):
            with contextlib.suppress(OSError):
                if old != folder and old.is_dir() and not old.is_symlink() and not old.is_junction() and old.stat().st_mtime < time.time()-7*86400:
                    shutil.rmtree(old, ignore_errors=True)
    return {"count": len(paths), "errors": errors}
