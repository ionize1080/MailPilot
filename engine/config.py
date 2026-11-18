import hashlib
import json
import os
import winreg
from pathlib import Path

HOME = Path(os.environ.get("MAILPILOT_HOME") or Path(os.environ["LOCALAPPDATA"]) / "MailPilot")
DEFAULTS = json.loads(Path(__file__).with_name("preferences.json").read_text(encoding="utf-8")) | {
    "indexDir": str(HOME / "Index"), "chatDir": str(HOME / "Chatbox")}

def settings():
    path = HOME / "settings.json"
    cfg = DEFAULTS | (json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {})
    if os.environ.get("MAILPILOT_SOURCE") in ("classic", "graph"):
        cfg["source"] = os.environ["MAILPILOT_SOURCE"]
    return cfg

def identity(cfg):
    if cfg["source"] == "graph":
        account = HOME / "graph-account.json"
        if not account.exists():
            raise ValueError("请先在设置中连接 Microsoft 邮箱。")
        identity_data = json.loads(account.read_text(encoding="utf-8"))
        if identity_data["clientId"] != cfg["clientId"]:
            raise ValueError("应用 ID 已变更，请重新连接 Microsoft 邮箱。")
        return "graph/" + identity_data["account"]
    profile = ""
    for version in ("16.0", "15.0", "14.0"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\Office\{version}\Outlook") as key:
                profile = winreg.QueryValueEx(key, "DefaultProfile")[0]
                break
        except OSError:
            pass
    if not profile:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Windows Messaging Subsystem\Profiles") as key:
                profile = winreg.QueryValueEx(key, "DefaultProfile")[0]
        except OSError:
            profile = "Outlook"
    return "classic/" + profile.casefold() + "/" + cfg["storeScope"]

def db_path(cfg):
    name = hashlib.sha256(identity(cfg).encode()).hexdigest()[:24]
    return Path(cfg["indexDir"]).expanduser().resolve() / ("mail-" + name + ".sqlite3")
