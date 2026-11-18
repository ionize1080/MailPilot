"""Microsoft delegated Mail.Read. Device sign-in runs only at the user's request."""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from config import HOME
from indexdb import save, state, set_state

LOGIN = "https://login.microsoftonline.com/common/oauth2/v2.0/"
API = "https://graph.microsoft.com/v1.0"
SCOPE = "offline_access https://graph.microsoft.com/Mail.Read"
def request(url, data=None, headers=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=35) as resp:
        return json.load(resp)

def account_file():
    return HOME / "graph-account.json"

def store_token(client, token, account):
    import win32crypt
    HOME.mkdir(parents=True, exist_ok=True)
    encrypted = win32crypt.CryptProtectData(token.encode(), "MailPilot Graph", None, None, None, 0)
    path = account_file()
    temp = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(dict(clientId=client, account=account,
                                    token=base64.b64encode(encrypted).decode())), encoding="utf-8")
    os.replace(temp, path)

def login(client, show):
    client = str(uuid.UUID(client))
    info = request(LOGIN + "devicecode", dict(client_id=client, scope=SCOPE))
    show(info["verification_uri"], info["user_code"])
    deadline = time.monotonic()+info["expires_in"]
    delay = info.get("interval",5)
    while time.monotonic() < deadline:
        time.sleep(delay)
        try:
            token = request(LOGIN+"token", dict(client_id=client, device_code=info["device_code"],
                            grant_type="urn:ietf:params:oauth:grant-type:device_code"))
        except urllib.error.HTTPError as e:
            code = json.load(e).get("error")
            if code == "slow_down":
                delay += 5
            elif code != "authorization_pending":
                raise ValueError("Microsoft 登录失败：" + str(code)) from None
            continue
        # Establish the account identity via a Graph mailbox ID, without requesting User.Read.
        result = request(API+"/me/mailFolders/inbox?$select=id", headers={"Authorization":"Bearer "+token["access_token"]})
        store_token(client, token["refresh_token"], result["id"])
        return
    raise ValueError("登录代码已过期，请重试。")

def sync(db, cfg, progress, cancel):
    import win32crypt
    info = json.loads(account_file().read_text(encoding="utf-8"))
    def refresh():
        encrypted = base64.b64decode(info["token"])
        secret = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode()
        token = request(LOGIN+"token", dict(client_id=cfg["clientId"], grant_type="refresh_token",
                                            refresh_token=secret, scope=SCOPE))
        if token.get("refresh_token"):
            store_token(cfg["clientId"], token["refresh_token"], info["account"])
            info.update(json.loads(account_file().read_text(encoding="utf-8")))
        return token["access_token"]
    access = refresh()
    def get(url):
        nonlocal access
        if urllib.parse.urlsplit(url).netloc != "graph.microsoft.com" or not url.startswith("https://"):
            raise ValueError("无效的 Microsoft Graph 分页地址。")
        for attempt in range(4):
            if cancel():
                raise InterruptedError("索引已暂停，可再次刷新。")
            try:
                return request(url, headers={"Authorization":"Bearer "+access,
                    "Prefer":'IdType="ImmutableId", outlook.body-content-type="text", odata.maxpagesize='+str(cfg["batchSize"])})
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    access = refresh()
                elif e.code in (429,503) and attempt < 3:
                    time.sleep(min(30,int(e.headers.get("Retry-After",2))))
                else:
                    raise
    return sync_pages(db, cfg, progress, get, info["account"])

def sync_pages(db, cfg, progress, get, account):
    quote = lambda s: urllib.parse.quote(s, safe="")
    checked = changed = removed = 0
    visited = set()
    def folders(url, parent):
        while url:
            page = get(url)
            for f in page["value"]:
                fid = f["id"]
                if fid in visited:
                    continue
                visited.add(fid)
                name = parent + "/" + f["displayName"]
                yield fid,name
                if f.get("childFolderCount"):
                    yield from folders(API+"/me/mailFolders/"+quote(fid)+"/childFolders?$select=id,displayName,childFolderCount", name)
            url = page.get("@odata.nextLink")
    for fid, path in folders(API+"/me/mailFolders?$select=id,displayName,childFolderCount",""):
        key = "delta/" + fid
        initial = API+"/me/mailFolders/"+quote(fid)+"/messages/delta?$select=id,changeKey"
        url = state(db, key) or initial
        restart = False
        while url:
            try:
                page = get(url)
            except urllib.error.HTTPError as e:
                if e.code == 410 and not restart:
                    # Keep the previous index until the replacement baseline completes.
                    restart = True
                    url = initial
                    db.execute("CREATE TEMP TABLE IF NOT EXISTS baseline(id TEXT PRIMARY KEY)")
                    db.execute("DELETE FROM baseline")
                    db.commit()
                    continue
                raise
            updates, deletions, seen = [], [], []
            for change in page["value"]:
                entry = change["id"]
                checked += 1
                if "@removed" in change:
                    deletions.append((account,entry,fid))
                    continue
                seen.append((entry,))
                murl = API+"/me/messages/"+quote(entry)
                try:
                    m = get(murl+"?$select=id,subject,from,receivedDateTime,changeKey,body,webLink,parentFolderId&$expand=attachments($select=name)")
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    deletions.append((account,entry,fid))
                    continue
                if m.get("parentFolderId",fid) != fid:
                    continue
                names = [a["name"] for a in m.get("attachments",[])]
                more = m.get("attachments@odata.nextLink")
                while more:
                    p = get(more)
                    names.extend(a["name"] for a in p["value"])
                    more = p.get("@odata.nextLink")
                updates.append(dict(store=account,entry=entry,folder=path,folder_id=fid,subject=m.get("subject") or "",
                    body=(m.get("body") or {}).get("content") or "",sender=((m.get("from") or {}).get("emailAddress") or {}).get("name",""),
                    attachments=names,stamp=m["changeKey"],received=m.get("receivedDateTime",""),link=m.get("webLink","")))
            with db:
                for args in deletions:
                    removed += db.execute("DELETE FROM mail WHERE store=? AND entry=? AND folder_id=?",args).rowcount
                for item in updates:
                    save(db,item)
                if restart:
                    db.executemany("INSERT OR IGNORE INTO baseline VALUES(?)",seen)
                next_page = page.get("@odata.nextLink")
                if not next_page and restart:
                    removed += db.execute("DELETE FROM mail WHERE store=? AND folder_id=? AND entry NOT IN (SELECT id FROM baseline)",(account,fid)).rowcount
                # Persist only completed delta rounds so a cancelled baseline can be replayed.
                if not next_page:
                    db.execute("INSERT OR REPLACE INTO state VALUES(?,?)",(key,json.dumps(page["@odata.deltaLink"])))
                url = next_page
            changed += len(updates)
            progress(checked,changed,0)
            time.sleep(cfg["pauseMs"]/1000)
        with db:
            db.execute("UPDATE mail SET folder=? WHERE store=? AND folder_id=? AND folder<>?",(path,account,fid,path))
    with db:
        for (fid,) in list(db.execute("SELECT DISTINCT folder_id FROM mail WHERE store=?",(account,))):
            if fid not in visited:
                removed += db.execute("DELETE FROM mail WHERE store=? AND folder_id=?",(account,fid)).rowcount
                db.execute("DELETE FROM state WHERE key=?",("delta/"+fid,))
    return dict(checked=checked,changed=changed,removed=removed,errors=0)
