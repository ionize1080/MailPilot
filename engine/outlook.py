import ctypes
import datetime
import base64
import mimetypes
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path
import tempfile
import pythoncom
from message import person, repair_surrogates, values

def utc(dt):
    if dt is None:
        return ""
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="microseconds")

def optional(get, default=""):
    try:
        return get() or default
    except (pythoncom.com_error, AttributeError, ValueError, OverflowError):
        return default


def mapi(obj, tag):
    return optional(lambda: obj.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x" + tag))


def smtp(address_entry, fallback=""):
    if not address_entry:
        return fallback
    if optional(lambda: address_entry.Type) == "EX":
        return (mapi(address_entry, "39FE001F") or optional(lambda: address_entry.GetExchangeUser().PrimarySmtpAddress)
                or optional(lambda: address_entry.GetExchangeDistributionList().PrimarySmtpAddress) or fallback)
    return optional(lambda: address_entry.Address, fallback)


def rich_text_body(item, images):
    # Outlook's MHTML exporter converts its native RTF and packages inline artwork.
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"message.mht"
        item.SaveAs(str(path), 10)
        with path.open("rb") as stream:
            doc = BytesParser(policy=policy.default).parse(stream)
        body = doc.get_body(preferencelist=("html",))
        if body is None:
            return ""
        for part in doc.walk():
            mime = part.get_content_type()
            if mime not in ("image/png","image/jpeg","image/gif","image/webp","image/bmp"):
                continue
            content = part.get_payload(decode=True)
            if content:
                value = "data:"+mime+";base64,"+base64.b64encode(content).decode("ascii")
                for key in (part.get("Content-ID","").strip("<> "), part.get("Content-Location","")):
                    if key:
                        images[key] = value
        return body.get_content()


def read_item(ns, store, entry, folder, folder_id, stamp):
    item = ns.GetItemFromID(entry, store)
    sender = optional(lambda: item.SenderName)
    actual = person(sender, mapi(item, "5D01001F") or smtp(optional(lambda: item.Sender), optional(lambda: item.SenderEmailAddress)))
    represented = person(mapi(item, "0042001F") or optional(lambda: item.SentOnBehalfOfName), mapi(item, "5D02001F"))
    fields = {"sender": values(represented if represented and (represented != sender or not actual) else actual)}
    if actual and actual not in fields["sender"]:
        fields["onBehalf"] = [actual]
    recipients = item.Recipients
    for i in range(1, recipients.Count+1):
        r = recipients.Item(i)
        role = {1:"to", 2:"cc", 3:"bcc"}.get(r.Type, "to")
        fields.setdefault(role, []).append(person(optional(lambda: r.Name), smtp(optional(lambda: r.AddressEntry), optional(lambda: r.Address))))
    for key, attr in (("to","To"), ("cc","CC"), ("bcc","BCC"), ("replyTo","ReplyRecipientNames"),
                      ("categories","Categories"), ("conversation","ConversationTopic"),
                      ("flag","FlagRequest"), ("voting","VotingOptions"), ("vote","VotingResponse"),
                      ("billing","BillingInformation"), ("companies","Companies"), ("class","MessageClass"),
                      ("receivedBy","ReceivedByName"), ("receivedFor","ReceivedOnBehalfOfName"),
                      ("recipientId","ReceivedByEntryID"), ("flagIcon","FlagIcon")):
        if not fields.get(key):
            fields[key] = values(optional(lambda: getattr(item,attr)))
    replies = optional(lambda: item.ReplyRecipients, None)
    if replies and replies.Count:
        fields["replyTo"] = [person(r.Name, smtp(optional(lambda: r.AddressEntry), optional(lambda: r.Address)))
                             for r in (replies.Item(i) for i in range(1, replies.Count+1))]
    for key, attr in (("sent","SentOn"), ("created","CreationTime"), ("modified","LastModificationTime"),
                      ("expires","ExpiryTime"), ("due","TaskDueDate"), ("start","TaskStartDate"), ("reminder","ReminderTime")):
        when = optional(lambda: getattr(item, attr), None)
        if when and when.year < 4500:
            fields[key] = [utc(when)]
    fields["importance"] = values({0:"低",1:"普通",2:"高"}.get(optional(lambda:item.Importance, 0)))
    fields["sensitivity"] = values({0:"普通",1:"个人",2:"私人",3:"机密"}.get(optional(lambda:item.Sensitivity, 0)))
    fields["size"] = values(str(item.Size))
    fields["status"] = values("草稿" if not item.Sent else "", "未读" if item.UnRead else "已读",
                              "请求已读回执" if optional(lambda:item.ReadReceiptRequested) else "",
                              "请求送达回执" if optional(lambda:item.OriginatorDeliveryReportRequested) else "")
    for key, tag in (("headers","007D001F"), ("messageId","1035001F"), ("inReplyTo","1042001F"),
                     ("references","1039001F"), ("conversationId","30130102")):
        value = mapi(item, tag)
        fields[key] = values(value.hex() if isinstance(value, bytes) else value)
    if not fields["headers"]:
        fields["headers"] = values(mapi(item, "007D001E"))
    props = optional(lambda: item.UserProperties, None)
    if props:
        for i in range(1, props.Count+1):
            prop = props.Item(i)
            fields["custom:" + str(prop.Name)] = values(optional(lambda: prop.Value))
    files, images = [], {}
    attachments = item.Attachments
    for i in range(1, attachments.Count+1):
        a = attachments.Item(i)
        name = str(a.FileName or optional(lambda:a.DisplayName))
        cid, location = mapi(a, "3712001F").strip("<> "), mapi(a, "3713001F")
        mime = mapi(a, "370E001F") or mimetypes.guess_type(name)[0] or ""
        files.append(dict(name=name, size=optional(lambda:a.Size, 0), type=mime, cid=cid, location=location))
        if (cid or location) and mime.lower() in ("image/png","image/jpeg","image/gif","image/webp","image/bmp"):
            data = mapi(a, "37010102")
            if isinstance(data, (bytes, bytearray, memoryview)):
                images[cid or location] = "data:"+mime+";base64,"+base64.b64encode(data).decode("ascii")
    fields = {k:v for k,v in fields.items() if v}
    fields["files"] = files
    fmt = optional(lambda:item.BodyFormat)
    html = optional(lambda:item.HTMLBody) if fmt in (2,3) else ""
    if fmt == 3:
        try:
            html = rich_text_body(item, images) or html
        except (pythoncom.com_error, OSError, ValueError, LookupError):
            pass
    return dict(store=store, entry=entry, folder=folder, folder_id=folder_id, stamp=stamp,
                subject=str(item.Subject or ""), sender=sender or represented, received=utc(item.ReceivedTime),
                body=str(item.Body or ""), attachments=[f["name"] for f in files], metadata=fields,
                html=html, inlineImages=images)

def namespace():
    import win32com.client.dynamic
    return win32com.client.dynamic.Dispatch("Outlook.Application").GetNamespace("MAPI")

def sync(db, cfg, progress, cancel, selected_stores=None):
    import pythoncom
    from indexdb import save
    ctypes.OleDLL("ole32").CoInitializeEx(None, 2)
    try:
        ns = namespace()
        stores = ns.Stores
        selected = selected_stores if selected_stores is not None else (
            [ns.DefaultStore] if cfg["storeScope"] == "default" else [stores.Item(i) for i in range(1,stores.Count+1)])
        db.execute("CREATE TEMP TABLE IF NOT EXISTS seen(entry TEXT PRIMARY KEY) WITHOUT ROWID")
        visited_stores, visited_folders = set(), set()
        checked = changed = removed = errors = 0
        batch_size = max(1, min(512, cfg["batchSize"]))
        def walk(folder, sid):
            nonlocal checked, changed, removed, errors
            if cancel():
                raise InterruptedError("索引已暂停，可再次刷新。")
            fid = str(folder.EntryID)
            if (sid, fid) in visited_folders:
                return
            visited_folders.add((sid, fid))
            if folder.DefaultItemType == 0:
                path = repair_surrogates(str(folder.FolderPath))
                table = folder.GetTable()
                cols = table.Columns
                cols.RemoveAll()
                for col in ("EntryID","LastModificationTime","MessageClass","Size"):
                    cols.Add(col)
                try:
                    # PR_CHANGE_KEY detects even same-size edits within the same second.
                    cols.Add("http://schemas.microsoft.com/mapi/proptag/0x65E20102")
                except pythoncom.com_error:
                    pass
                db.execute("DELETE FROM seen")
                db.commit()
                while not table.EndOfTable:
                    if cancel():
                        raise InterruptedError("索引已暂停，可再次刷新。")
                    rows = table.GetArray(batch_size)
                    if not rows:
                        if not table.EndOfTable:
                            raise RuntimeError("Outlook 未返回下一批邮件。")
                        break
                    batch, keys = [], []
                    for entry, modified, kind, size, *extra in rows:
                        if not str(kind).lower().startswith("ipm.note"):
                            continue
                        entry, stamp = str(entry), utc(modified) + "/" + str(size)
                        change = extra[0] if extra else None
                        if isinstance(change, (bytes, bytearray, memoryview)) and len(change):
                            stamp += "/" + bytes(change).hex()
                        elif modified and abs(time.time() - modified.timestamp()) < 2:
                            # Some stores expose only whole-second stamps. Recheck an unsettled row once.
                            stamp += "/recent/" + str(time.time_ns())
                        keys.append((entry,))
                        checked += 1
                        old = db.execute("SELECT stamp,folder_id,folder FROM mail WHERE store=? AND entry=?", (sid,entry)).fetchone()
                        if old and tuple(old) == (stamp,fid,path):
                            continue
                        try:
                            batch.append(read_item(ns, sid, entry, path, fid, stamp))
                        except pythoncom.com_error:
                            errors += 1
                    with db:
                        db.executemany("INSERT OR IGNORE INTO seen VALUES(?)", keys)
                        for item in batch:
                            save(db, item)
                    changed += len(batch)
                    progress(checked, changed, errors)
                    if cfg["pauseMs"]:
                        time.sleep(cfg["pauseMs"]/1000)
                with db:
                    removed += db.execute("""DELETE FROM mail WHERE store=? AND folder_id=?
                        AND entry NOT IN (SELECT entry FROM seen)""",(sid,fid)).rowcount
            children = folder.Folders
            for n in range(1,children.Count+1):
                walk(children.Item(n), sid)
        for store in selected:
            sid = str(store.StoreID)
            visited_stores.add(sid)
            walk(store.GetRootFolder(), sid)
        if not visited_stores:
            raise ValueError("Outlook 未打开可读取的邮件存储区。")
        # Reconcile vanished folders and detached stores only after an uninterrupted enumeration.
        with db:
            for sid,fid in list(db.execute("SELECT DISTINCT store,folder_id FROM mail")):
                if (sid,fid) not in visited_folders:
                    removed += db.execute("DELETE FROM mail WHERE store=? AND folder_id=?", (sid,fid)).rowcount
        return dict(checked=checked, changed=changed, removed=removed, errors=errors)
    finally:
        ctypes.windll.ole32.CoUninitialize()

def open_item(store, entry):
    import pythoncom
    ctypes.OleDLL("ole32").CoInitializeEx(None, 2)
    try:
        namespace().GetItemFromID(entry, store).Display(False)
    finally:
        ctypes.windll.ole32.CoUninitialize()
