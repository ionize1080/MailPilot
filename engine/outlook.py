import ctypes
import datetime
import time

def utc(dt):
    if dt is None:
        return ""
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="microseconds")

def read_item(ns, store, entry, folder, folder_id, stamp):
    item = ns.GetItemFromID(entry, store)
    names = item.Attachments
    return dict(store=store, entry=entry, folder=folder, folder_id=folder_id, stamp=stamp,
                subject=str(item.Subject or ""), sender=str(item.SenderName or ""), received=utc(item.ReceivedTime),
                body=str(item.Body or ""), attachments=[str(names.Item(i).FileName) for i in range(1,names.Count+1)])

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
                path = str(folder.FolderPath)
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
