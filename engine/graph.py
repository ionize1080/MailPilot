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
from indexdb import save, state, rename_folder
from message import html_text, person, values

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

def graph_connection(cfg, cancel=lambda: False):
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
    def get(url, destination=None):
        nonlocal access
        if urllib.parse.urlsplit(url).netloc != "graph.microsoft.com" or not url.startswith("https://"):
            raise ValueError("无效的 Microsoft Graph 分页地址。")
        for attempt in range(4):
            if cancel():
                raise InterruptedError("索引已暂停，可再次刷新。")
            try:
                headers = {"Authorization":"Bearer "+access,
                    "Prefer":'IdType="ImmutableId", outlook.body-content-type="html", odata.maxpagesize='+str(cfg["batchSize"])}
                if destination is None:
                    return request(url, headers=headers)
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response, destination.open("wb") as out:
                    while chunk := response.read(256 * 1024):
                        if cancel():
                            raise InterruptedError("下载已取消。")
                        out.write(chunk)
                    length = response.headers.get("Content-Length")
                    if length is not None and out.tell() != int(length):
                        raise IOError("附件下载中断，请重试。")
                return
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    access = refresh()
                elif e.code in (429,503) and attempt < 3:
                    time.sleep(min(30,int(e.headers.get("Retry-After",2))))
                else:
                    raise
    return get, info["account"]

def sync(db, cfg, progress, cancel):
    get, account = graph_connection(cfg, cancel)
    return sync_pages(db, cfg, progress, get, account)

def list_attachments(murl, get):
    url = murl + "/attachments?$select=id,name,contentType,size,isInline"
    attachments = []
    while url:
        page = get(url)
        attachments.extend(page["value"])
        url = page.get("@odata.nextLink")
    return attachments

def attachment_reader(cfg, row, cancel=lambda: False):
    get, account = graph_connection(cfg, cancel)
    if account != row["store"]:
        raise ValueError("邮箱已切换，请重新查找。")
    murl = API + "/me/messages/" + urllib.parse.quote(row["entry"], safe="")
    legacy = None
    def fetch(index, file, destination):
        nonlocal legacy
        identity, kind = file.get("graphId"), file.get("kind")
        if not identity:
            if legacy is None:
                if row["stamp"] and get(murl + "?$select=changeKey")["changeKey"] != row["stamp"]:
                    raise ValueError("原邮件已更改，请刷新索引后重试。")
                legacy = list_attachments(murl, get)
            matches = [a for a in legacy if a.get("name") == file["name"] and
                       (file.get("size") is None or a.get("size") == file["size"])]
            if len(matches) == 1:
                current = matches[0]
            elif row["stamp"] and index < len(legacy) and legacy[index] in matches:
                current = legacy[index]
            else:
                raise ValueError("无法辨认原附件，请在 Outlook 原件中查看。")
            identity, kind = current["id"], current.get("@odata.type")
        if kind == "#microsoft.graph.referenceAttachment":
            raise ValueError("这是云端链接附件，请在 Outlook 原件中打开。")
        url = murl + "/attachments/" + urllib.parse.quote(identity, safe="") + "/$value"
        try:
            get(url, destination)
        except urllib.error.HTTPError as e:
            if e.code == 405:
                raise ValueError("这是云端链接附件，请在 Outlook 原件中打开。") from None
            if e.code == 404:
                raise ValueError("原附件已移动或删除，请刷新索引。") from None
            raise
    return fetch

def graph_person(value):
    entry = (value or {}).get("emailAddress") or {}
    return person(entry.get("name"), entry.get("address"))


def message_record(m, attachments, murl, get):
    author, sender = graph_person(m.get("from")), graph_person(m.get("sender"))
    fields = {"sender": values(author or sender), "onBehalf": values(sender if author and author != sender else ""),
              "categories": m.get("categories", [])}
    for key, prop in (("to","toRecipients"), ("cc","ccRecipients"), ("bcc","bccRecipients"), ("replyTo","replyTo")):
        fields[key] = [graph_person(v) for v in m.get(prop, [])]
    for key, prop in (("sent","sentDateTime"), ("created","createdDateTime"), ("modified","lastModifiedDateTime"),
                      ("messageId","internetMessageId"), ("conversationId","conversationId"), ("link","webLink"),
                      ("conversationIndex","conversationIndex"), ("classification","inferenceClassification")):
        fields[key] = values(m.get(prop))
    fields["importance"] = values({"low":"低","normal":"普通","high":"高"}.get(m.get("importance")))
    fields["status"] = values("草稿" if m.get("isDraft") else "", "已读" if m.get("isRead") else "未读",
                              "请求已读回执" if m.get("isReadReceiptRequested") else "",
                              "请求送达回执" if m.get("isDeliveryReceiptRequested") else "")
    flag = m.get("flag") or {}
    fields["flag"] = values({"flagged":"已标记","complete":"已完成"}.get(flag.get("flagStatus")))
    for key, prop in (("due","dueDateTime"), ("start","startDateTime"), ("completed","completedDateTime")):
        date = flag.get(prop) or {}
        fields[key] = values(" ".join(filter(None, (date.get("dateTime"), date.get("timeZone")))))
    fields["headers"] = values("\r\n".join(h["name"]+": "+h["value"] for h in m.get("internetMessageHeaders", [])))
    for prop in m.get("singleValueExtendedProperties", []):
        tag = prop["id"].lower().split()[-1]
        if tag in ("0x36","0x0036"):
            fields["sensitivity"] = values({"0":"普通","1":"个人","2":"私人","3":"机密"}.get(prop.get("value")))
        elif tag in ("0xe08","0x0e08"):
            fields["size"] = values(prop.get("value"))
    files, images = [], {}
    for a in attachments:
        if a.get("isInline") and (a.get("contentType") or "").lower() in ("image/png","image/jpeg","image/gif","image/webp","image/bmp") and a.get("id"):
            a = a | get(murl+"/attachments/"+urllib.parse.quote(a["id"], safe=""))
        cid, loc = (a.get("contentId") or "").strip("<> "), a.get("contentLocation") or ""
        if (cid or loc) and a.get("contentBytes"):
            images[cid or loc] = "data:"+a["contentType"]+";base64,"+a["contentBytes"]
        files.append(dict(name=a.get("name") or "", type=a.get("contentType") or "", size=a.get("size"),
                          cid=cid, location=loc, graphId=a.get("id"), kind=a.get("@odata.type")))
    fields = {k:v for k,v in fields.items() if v}
    fields["files"] = files
    body = m.get("body") or {}
    content = body.get("content") or ""
    rich = (body.get("contentType") or "").lower()=="html"
    return dict(subject=m.get("subject") or "", sender=((m.get("from") or {}).get("emailAddress") or {}).get("name") or author or sender,
                received=m.get("receivedDateTime",""), stamp=m["changeKey"], link=m.get("webLink",""), metadata=fields,
                body=html_text(content) if rich else content, html=content if rich else "", inlineImages=images,
                attachments=[f["name"] for f in files])


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
        token = state(db, key)
        url = token or initial
        baseline = not token
        restart = False
        db.execute("CREATE TEMP TABLE IF NOT EXISTS baseline(id TEXT PRIMARY KEY)")
        with db:
            db.execute("DELETE FROM baseline")
        while url:
            try:
                page = get(url)
            except urllib.error.HTTPError as e:
                if e.code == 410 and not restart:
                    # Keep the previous index until the replacement baseline completes.
                    restart = True
                    baseline = True
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
                    m = get(murl+"?$select=id,subject,from,sender,toRecipients,ccRecipients,bccRecipients,replyTo,"
                            "sentDateTime,receivedDateTime,createdDateTime,lastModifiedDateTime,changeKey,body,webLink,"
                            "parentFolderId,categories,importance,isRead,isDraft,isReadReceiptRequested,isDeliveryReceiptRequested,"
                            "internetMessageHeaders,internetMessageId,conversationId,conversationIndex,inferenceClassification,flag"
                            "&$expand=singleValueExtendedProperties($filter=id%20eq%20'Integer%200x36'%20or%20id%20eq%20'Integer%200xE08')")
                    attachments = list_attachments(murl, get)
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    deletions.append((account,entry,fid))
                    continue
                if m.get("parentFolderId",fid) != fid:
                    continue
                updates.append(message_record(m, attachments, murl, get) | dict(store=account,entry=entry,folder=path,folder_id=fid))
            with db:
                for args in deletions:
                    removed += db.execute("DELETE FROM mail WHERE store=? AND entry=? AND folder_id=?",args).rowcount
                for item in updates:
                    save(db,item)
                if baseline:
                    db.executemany("INSERT OR IGNORE INTO baseline VALUES(?)",seen)
                next_page = page.get("@odata.nextLink")
                if not next_page and baseline:
                    removed += db.execute("DELETE FROM mail WHERE store=? AND folder_id=? AND entry NOT IN (SELECT id FROM baseline)",(account,fid)).rowcount
                # Persist only completed delta rounds so a cancelled baseline can be replayed.
                if not next_page:
                    db.execute("INSERT OR REPLACE INTO state VALUES(?,?)",(key,json.dumps(page["@odata.deltaLink"])))
                url = next_page
            changed += len(updates)
            progress(checked,changed,0)
            time.sleep(cfg["pauseMs"]/1000)
        with db:
            rename_folder(db, account, fid, path)
    with db:
        for (fid,) in list(db.execute("SELECT DISTINCT folder_id FROM mail WHERE store=?",(account,))):
            if fid not in visited:
                removed += db.execute("DELETE FROM mail WHERE store=? AND folder_id=?",(account,fid)).rowcount
                db.execute("DELETE FROM state WHERE key=?",("delta/"+fid,))
    return dict(checked=checked,changed=changed,removed=removed,errors=0)
