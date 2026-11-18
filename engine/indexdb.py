import json
import sqlite3
import time
import zlib
from pathlib import Path

import re

# ASCII simple case equivalents also include the four non-ASCII letters below.
FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZİıſK\x00", "abcdefghijklmnopqrstuvwxyziisk ")
HAN = re.compile(r"[\u3400-\u9fff]")
def terms(text):
    # Inserting a separator before Han characters makes two-character Chinese terms indexable.
    return HAN.sub(lambda m: "\x1f" + m[0], text.translate(FOLD))

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
    if db.execute("PRAGMA user_version").fetchone()[0] == 0:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nPRAGMA user_version=1; COMMIT;")
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

def save(db, item):
    row = db.execute("""INSERT INTO mail(store,entry,folder_id,folder,stamp,subject,sender,received,body,attachments,link)
        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(store,entry) DO UPDATE SET
        folder_id=excluded.folder_id,folder=excluded.folder,stamp=excluded.stamp,subject=excluded.subject,
        sender=excluded.sender,received=excluded.received,body=excluded.body,
        attachments=excluded.attachments,link=excluded.link RETURNING id""",
        (item["store"], item["entry"], item["folder_id"], item["folder"], item["stamp"],
         item["subject"], item["sender"], item["received"], pack_body(item["body"]),
         json.dumps(item["attachments"], ensure_ascii=False), item.get("link", ""))).fetchone()[0]
    db.execute("DELETE FROM grams WHERE rowid=?", (row,))
    db.execute("INSERT INTO grams(rowid,subject,body,attachment) VALUES(?,?,?,?)",
               (row, terms(item["subject"]), terms(item["body"]), terms("\n".join(item["attachments"]))))
    return row

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
