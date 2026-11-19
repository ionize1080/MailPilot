import json
import hashlib
import ctypes
import datetime
from functools import lru_cache
import sqlite3
import time
import zlib
from pathlib import Path

import re
from message import BodyText, message_fields, repair_surrogates

# ASCII simple case equivalents also include the four non-ASCII letters below.
FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZİıſK\x00", "abcdefghijklmnopqrstuvwxyziisk ")
HAN = re.compile(r"[\u3400-\u9fff]")
def terms(text):
    # Inserting a separator before Han characters makes two-character Chinese terms indexable.
    return HAN.sub(lambda m: "\x1f" + m[0], text.translate(FOLD))

# Use Windows' Simplified Chinese dictionary order for names and subjects, including numeric runs.
_map_string = ctypes.WinDLL("kernel32", use_last_error=True).LCMapStringEx
_map_string.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_int,
                        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t]

@lru_cache(maxsize=2048)
def text_order(value):
    value = value.strip().replace("\0", " ")
    flags = 0x400 | 0x1 | 0x8  # LCMAP_SORTKEY, NORM_IGNORECASE, SORT_DIGITSASNUMBERS
    size = _map_string("zh-CN", flags, value, -1, None, 0, None, None, 0)
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buf = ctypes.create_string_buffer(size)
    if not _map_string("zh-CN", flags, value, -1, buf, size, None, None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return buf.raw

def date_order(value):
    try:
        stamp = datetime.datetime.fromisoformat(value)
        if stamp.tzinfo:
            stamp = stamp.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return stamp.isoformat(timespec="microseconds")
    except (ValueError, OverflowError):
        return value

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail(
 id INTEGER PRIMARY KEY AUTOINCREMENT, store TEXT NOT NULL, entry TEXT NOT NULL, folder_id TEXT NOT NULL,
 folder TEXT NOT NULL, stamp TEXT NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,
 received TEXT NOT NULL, body BLOB NOT NULL, attachments TEXT NOT NULL, link TEXT NOT NULL,
 UNIQUE(store,entry));
CREATE INDEX IF NOT EXISTS mail_date ON mail(received DESC,id DESC);
CREATE INDEX IF NOT EXISTS mail_folder ON mail(store,folder_id);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS grams USING fts5(subject,body,attachment,
 content='',contentless_delete=1,detail=column,tokenize='trigram case_sensitive 1');
CREATE TRIGGER IF NOT EXISTS mail_removed AFTER DELETE ON mail BEGIN
 DELETE FROM grams WHERE rowid=old.id;
END;
"""

def connect(path, cache=8):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=12)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=12000")
    db.execute("PRAGMA cache_size=" + str(-1024 * max(1, min(int(cache), 64))))
    db.execute("PRAGMA temp_store=FILE")
    if db.execute("PRAGMA user_version").fetchone()[0] < 2:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] < 2:
                db.execute("ALTER TABLE mail ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
                db.execute("ALTER TABLE mail ADD COLUMN html BLOB")
                db.execute("ALTER TABLE mail ADD COLUMN inline_images BLOB")
                db.execute("""CREATE VIRTUAL TABLE envelope USING fts5(sender,other,
                    content='',contentless_delete=1,detail=column,tokenize='trigram case_sensitive 1')""")
                db.execute("""CREATE TRIGGER envelope_removed AFTER DELETE ON mail BEGIN
                    DELETE FROM envelope WHERE rowid=old.id; END""")
                db.create_function("grams_text", 1, terms)
                db.execute("""INSERT INTO envelope(rowid,sender,other)
                    SELECT id,grams_text(sender),grams_text(received||char(10)||folder) FROM mail""")
                # Existing rows remain readable while each mailbox is enriched on its next refresh.
                db.execute("UPDATE mail SET stamp=''")
                db.execute("DELETE FROM state WHERE key LIKE 'delta/%' OR key='lastSync'")
                db.execute("PRAGMA user_version=2")
            db.commit()
        except Exception:
            db.rollback()
            db.close()
            raise
    if db.execute("PRAGMA user_version").fetchone()[0] < 3:
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] < 3:
                db.execute("ALTER TABLE mail ADD COLUMN date_sort TEXT NOT NULL DEFAULT ''")
                db.execute("ALTER TABLE mail ADD COLUMN sender_sort BLOB NOT NULL DEFAULT X''")
                db.execute("ALTER TABLE mail ADD COLUMN subject_sort BLOB NOT NULL DEFAULT X''")
                db.create_function("date_order", 1, date_order)
                db.create_function("text_order", 1, text_order)
                db.execute("UPDATE mail SET date_sort=date_order(received), sender_sort=text_order(sender), subject_sort=text_order(subject)")
                db.execute("CREATE INDEX mail_received_order ON mail(date_sort DESC,id DESC)")
                for column in ("sender_sort", "subject_sort"):
                    db.execute(f"CREATE INDEX mail_{column} ON mail({column},date_sort DESC,id DESC)")
                db.execute("DROP INDEX IF EXISTS mail_date")
                db.execute("PRAGMA user_version=3")
            db.commit()
        except Exception:
            db.rollback()
            db.close()
            raise
    db.execute("PRAGMA synchronous=NORMAL")
    return db

def pack_body(text):
    data = text.encode("utf-8", "replace")
    if len(data) >= 384:
        packed = zlib.compress(data, 1)
        if len(packed) < len(data):
            return b"Z" + packed
    return b"T" + data

def unpack_body(blob):
    return (zlib.decompress(blob[1:]) if blob[:1] == b"Z" else blob[1:]).decode("utf-8")

def mail_key(store, entry):
    return hashlib.sha256((store+"\0"+entry).encode("utf-8")).hexdigest()[:32]

def save(db, item):
    # The stored snapshot and both full-text indexes must use the same repaired text.
    item = repair_surrogates(item)
    meta = dict(item.get("metadata", {}))
    html, images = item.get("html"), item.get("inlineImages")
    if html:
        markup = BodyText()
        markup.feed(html)
        markup.close()
        if markup.links:
            meta["links"] = list(markup.links)
        if markup.alternatives:
            meta["imageAlt"] = list(markup.alternatives)
    row = db.execute("""INSERT INTO mail(store,entry,folder_id,folder,stamp,subject,sender,received,body,attachments,link,metadata,html,inline_images,date_sort,sender_sort,subject_sort)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(store,entry) DO UPDATE SET
        folder_id=excluded.folder_id,folder=excluded.folder,stamp=excluded.stamp,subject=excluded.subject,
        sender=excluded.sender,received=excluded.received,body=excluded.body,
        attachments=excluded.attachments,link=excluded.link,metadata=excluded.metadata,
        html=excluded.html,inline_images=excluded.inline_images,date_sort=excluded.date_sort,
        sender_sort=excluded.sender_sort,subject_sort=excluded.subject_sort RETURNING id""",
        (item["store"], item["entry"], item["folder_id"], item["folder"], item["stamp"],
         item["subject"], item["sender"], item["received"], pack_body(item["body"]),
         json.dumps(item["attachments"], ensure_ascii=False), item.get("link", ""),
         json.dumps(meta, ensure_ascii=False), pack_body(html) if html else None,
         pack_body(json.dumps(images)) if images else None, date_order(item["received"]),
         text_order(item["sender"]), text_order(item["subject"]))).fetchone()[0]
    db.execute("DELETE FROM grams WHERE rowid=?", (row,))
    db.execute("INSERT INTO grams(rowid,subject,body,attachment) VALUES(?,?,?,?)",
               (row, terms(item["subject"]), terms(item["body"]), terms("\n".join(item["attachments"]))))
    fields = message_fields(item["subject"], item["sender"], item["received"], item["folder"], item["attachments"], meta)
    save_envelope(db, row, fields)
    return row


def save_envelope(db, row, fields):
    people = fields["sender"] + fields.get("onBehalf", [])
    other = (v for k, vs in fields.items() if k not in ("subject", "sender", "attachment", "onBehalf") for v in vs)
    db.execute("DELETE FROM envelope WHERE rowid=?", (row,))
    db.execute("INSERT INTO envelope(rowid,sender,other) VALUES(?,?,?)",
               (row, terms("\n".join(people)), terms("\n".join(other))))


def rename_folder(db, store, fid, path):
    path = repair_surrogates(path)
    for r in db.execute("SELECT * FROM mail WHERE store=? AND folder_id=? AND folder<>?", (store, fid, path)):
        fields = message_fields(r["subject"], r["sender"], r["received"], path, json.loads(r["attachments"]), json.loads(r["metadata"]))
        save_envelope(db, r["id"], fields)
    db.execute("UPDATE mail SET folder=? WHERE store=? AND folder_id=? AND folder<>?", (path, store, fid, path))

def set_state(db, key, value):
    with db:
        db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))

def state(db, key, default=None):
    row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default

def status(db):
    return {"count": db.execute("SELECT count(*) FROM mail").fetchone()[0],
            "lastSync": state(db, "lastSync", 0), "sync": state(db, "progress", {}),
            "time": int(time.time())}
