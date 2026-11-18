import contextlib
import json
import random
import sqlite3
import tempfile
import urllib.error
from pathlib import Path
from config import DEFAULTS
from graph import API, sync_pages
from indexdb import SCHEMA,connect,save,pack_body,unpack_body,terms,state
from search import MODES,search,query,highlights

def row(i, text):
    return dict(store="s",entry=str(i),folder="/in",folder_id="in",stamp="1",subject=text,
        body=text[::-1]+"\n"+text,attachments=["卷宗-"+text+".zip"],sender="QA",received=str(i).zfill(4))

def run():
    rng=random.Random(411)
    with tempfile.TemporaryDirectory() as tmp, contextlib.closing(connect(Path(tmp)/"mail.sqlite3")) as db:
        corpus=["TİTLE-01","TıTLE-02","ſeaKing","甲乙预算","财务","Ⅺ Plan","alpha-332","beta-121",
                "foobar","A\x00needle","RAVEN-首单","𠀀预算", "a single", "xxccc", "aaaaab"]
        corpus += [" ".join(rng.choices(corpus,k=4)) for _ in range(190)]
        with db:
            for i,v in enumerate(corpus): save(db,row(i,v))
        pats=[r"TITLE-\d+",r"title",r"seaking",r"预算|财务",r"甲乙.{0,3}预",r"alpha-[0-9]{3}",
              r"(alpha|beta)-\d+",r"(alpha)?beta",r"(?:foo)?bar",r"^A.needle",r"财务",r"𠀀预",
              r"(?<=alpha-)332",r"(?i)RAVEN",r"(?s)卷宗.*zip",r"\bPlan\b",r"首单$",r"foo{e<=1}",
              r"^.{1,4}$",r"\p{Han}{2}",r"a(?=lpha)",r"aaa+b",r"\d+",r"\x61lpha",r"[a-z]+",
              r"(?P<n>a)(?P=n)",r"(?:alpha|beta)?-?[0-9]",r"RAVEN-\D+?",r"(a|b)+a",r"ab\{2\}"]
        comparisons=0
        for p in pats:
            for mode in MODES:
                for cs in (False,True):
                    args=dict(pattern=p,mode=mode,caseSensitive=cs,limit=1000)
                    a=search(db,args,DEFAULTS); b=search(db,args,DEFAULTS,force_scan=True)
                    assert not a["partial"] and a["items"]==b["items"],(p,mode,cs)
                    comparisons+=1
        args=dict(pattern=".",mode="subject",limit=7)
        ids=[]; cursor=None
        while True:
            a=search(db,args|{"cursor":cursor},DEFAULTS); ids += [h["id"] for h in a["items"]];cursor=a["next"]
            if not cursor:break
        assert len(ids)==len(set(ids))==len(corpus)
        with db: save(db,row(1,"replacement"));db.execute("DELETE FROM mail WHERE entry='2'")
        assert len(search(db,dict(pattern="replacement",mode="all"),DEFAULTS)["items"])==1
        assert search(db,dict(pattern=".",mode="subject"),DEFAULTS,lambda:True)["partial"]
        print(f"PASS {comparisons} indexed/scan result comparisons, update, deletion reconciliation, pagination and cancellation")

def envelope():
    with tempfile.TemporaryDirectory() as tmp, contextlib.closing(connect(Path(tmp)/"fields.db")) as db:
        original = row(1,"采购")
        record = original | {"metadata":{"sender":["林 <lin@example.org>"],"onBehalf":["助理 <delegate@example.org>"],
            "to":["Project list"],"cc":["质量-Review"],"bcc":["Archive-only"],"sent":["2026-11-01"],
            "headers":["X-Trace: 📨INTERNET-QA"],"custom:采购单":["AF-7701"],"categories":["Astral 🔖"],
            "files":[{"name":original["attachments"][0],"type":"test/mimeonly","size":125}]}}
        with db: save(db,record)
        for pattern, field in (("@example","sender"),(r"^lin@example\.org$","sender"),("delegate@","onBehalf"),("Project list","to"),("质量","cc"),
                               ("Archive-only","bcc"),("INTERNET-QA","headers"),("AF-7701","custom:采购单"),
                               ("Astral","categories"),("mimeonly","attachmentType"),("2026-11","sent")):
            for mode in MODES:
                args=dict(pattern=pattern,mode=mode)
                a=search(db,args,DEFAULTS);b=search(db,args,DEFAULTS,force_scan=True)
                assert a["items"]==b["items"]
                if mode=="full" or mode=="sender" and field in ("sender","onBehalf"):
                    assert a["items"][0]["field"]==field
                else:
                    assert not a["items"],(mode,pattern)
        params=query(dict(mode="full",pattern=r"(?<=📨)A|(?=B)"),DEFAULTS)
        hit=highlights(*params,{"headers":["📨AB"]},DEFAULTS)
        assert hit["marks"]["headers"]==[[(2,3),(3,3)]]
        with db: save(db,original)
        assert not search(db,dict(pattern="Archive-only",mode="full"),DEFAULTS)["items"]
        print("PASS sender/delegate/full scope, metadata FTS updates, UTF-16 and zero-width highlighting")

def surrogate_mail():
    subject = "预算\ud83d\udce8📅"
    body = "x" * 217 + "\udd00BodyTail" + "正文" * 50
    attachment = "File\udfffName.xlsx"
    html = '<a href="https://example.org/\ud800link">link</a><img src="cid:pic\udd00" alt="Alt\udd00Text">'
    record = row(2, subject) | {
        "body": body, "sender": "Sender\ud800Name", "folder": "/Folder\udd00Name", "html": html,
        "attachments": [attachment], "inlineImages": {"pic\udd00": "data:image/png;base64,AA=="},
        "metadata": {"custom:\ud800field": ["Value\ud800End"], "headers": ["Trace\udd00End"],
                     "files": [{"name": attachment, "size": 123, "cid": "pic\udd00"}]},
    }
    with tempfile.TemporaryDirectory() as tmp, contextlib.closing(connect(Path(tmp)/"unicode.db")) as db:
        with db:
            save(db, row(1, "Before"))
            rid = save(db, record)
            save(db, row(3, "After"))
        assert db.execute("SELECT count(*) FROM mail").fetchone()[0] == 3
        stored = db.execute("SELECT * FROM mail WHERE id=?", (rid,)).fetchone()
        assert stored["subject"] == "预算📨📅"
        assert unpack_body(stored["body"]) == body.replace("\udd00", "\ufffd")
        assert unpack_body(stored["html"]) == html.replace("\ud800", "\ufffd").replace("\udd00", "\ufffd")
        assert json.loads(unpack_body(stored["inline_images"])) == {"pic\ufffd": "data:image/png;base64,AA=="}
        metadata = json.loads(stored["metadata"])
        assert metadata["files"] == [{"name": "File\ufffdName.xlsx", "size": 123, "cid": "pic\ufffd"}]
        for pattern, field in (("预算📨📅", "subject"), ("\ufffdBodyTail", "body"), ("File\ufffdName", "attachment"),
                               ("Sender\ufffdName", "sender"), ("Folder\ufffdName", "folder"), ("Trace\ufffdEnd", "headers"),
                               ("Value\ufffdEnd", "custom:\ufffdfield"), ("Alt\ufffdText", "imageAlt"), ("/\ufffdlink", "links")):
            args = dict(pattern=pattern, mode="full")
            indexed = search(db, args, DEFAULTS)
            assert indexed["items"] == search(db, args, DEFAULTS, force_scan=True)["items"]
            assert [(hit["id"], hit["field"]) for hit in indexed["items"]] == [(rid, field)], pattern
        print("PASS isolated surrogates, valid emoji, nested properties and same-batch mail search")

def upgrade():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"v1.db"
        with contextlib.closing(sqlite3.connect(path)) as old:
            old.executescript(SCHEMA+"PRAGMA user_version=1;")
            old.execute("INSERT INTO mail VALUES(1,'S','E','F','Legacy Inbox','V','Old Subject','Old Sender','2010',?,'[]','')",(pack_body("old body"),))
            old.execute("INSERT INTO grams(rowid,subject,body,attachment) VALUES(1,?,?,'')",(terms("Old Subject"),terms("old body")))
            old.execute("INSERT INTO state VALUES('lastSync','99'),('delta/F','\"old cursor\"')")
            old.commit()
        with contextlib.closing(connect(path)) as db:
            assert not state(db,"delta/F") and not state(db,"lastSync")
            for pattern,mode in [("Old Subject","subject"),("Old Sender","sender"),("Legacy Inbox","full"),("old body","full")]:
                assert search(db,dict(pattern=pattern,mode=mode),DEFAULTS)["items"][0]["id"]==1
            assert db.execute("SELECT stamp FROM mail").fetchone()[0]==""
        print("PASS v1 upgrade retains IDs/content and schedules envelope and HTML backfill")

def graph_rounds():
    f=API+"/me/mailFolders?$select=id,displayName,childFolderCount"
    delta=API+"/me/mailFolders/F/messages/delta?$select=id,changeKey"
    token=API+"/delta/1";next_token=API+"/delta/2"
    cfg=DEFAULTS|{"pauseMs":0}
    with tempfile.TemporaryDirectory() as tmp, contextlib.closing(connect(Path(tmp)/"m.db")) as db:
        deleted=False;expired=False;pages=[]
        folder_name="Inbox"
        def fetch(url):
            pages.append(url)
            if url==f:return {"value":[dict(id="F",displayName=folder_name,childFolderCount=0)]}
            if url==delta:return {"value":[{"id":"A"}] if not expired else [],"@odata.nextLink":API+"/page2"}
            if url==API+"/page2":return {"value":[],"@odata.deltaLink":token}
            if url in (token,next_token):
                if expired:raise urllib.error.HTTPError(url,410,"Gone",{},None)
                return {"value":[{"id":"A","@removed":{}}] if deleted else [],"@odata.deltaLink":next_token}
            if "/me/messages/A?" in url:return dict(id="A",subject="Graph message",changeKey="01",body={"contentType":"html","content":"<p>fi<b>xt</b>ure</p>"},
                ccRecipients=[{"emailAddress":{"name":"Archive","address":"cc@example.org"}}],internetMessageHeaders=[{"name":"X-Test","value":"Graph trace"}],
                singleValueExtendedProperties=[{"id":"Integer 0x0036","value":"3"},{"id":"Integer 0x0e08","value":"32121"}],parentFolderId="F")
            if "/me/messages/A/attachments?" in url:return {"value":[{"name":"Page1.xlsx"}],"@odata.nextLink":API+"/attach2"}
            if url==API+"/attach2":return {"value":[{"name":"Second.csv"},{"id":"I","name":"image.png","isInline":True,"contentType":"image/png"}]}
            if url==API+"/me/messages/A/attachments/I":return {"contentId":"signature", "contentBytes":"AA=="}
            raise AssertionError(url)
        def run():return sync_pages(db,cfg,lambda *args:None,fetch,"fixture")
        assert run()["changed"]==1
        assert search(db,dict(pattern=r"Second\.csv",mode="attachment"),DEFAULTS)["items"]
        for pattern in ("cc@example","Graph trace","fixture","机密","32121"):
            assert search(db,dict(pattern=pattern,mode="full"),DEFAULTS)["items"]
        assert all(db.execute("SELECT html,inline_images FROM mail").fetchone())
        folder_name="Renamed\udd00Folder"
        assert run()["changed"]==0 and pages.count(delta)==1
        renamed=search(db,dict(pattern="Renamed\ufffdFolder",mode="full"),DEFAULTS)["items"]
        assert len(renamed)==1 and renamed[0]["field"]=="folder"
        deleted=True
        assert run()["removed"]==1
        with db:save(db,row(3,"old")|{"store":"fixture","folder_id":"F"})
        expired=True
        assert run()["removed"]==1 and db.execute("SELECT count(*) FROM mail").fetchone()[0]==0
        print("PASS Graph folder, delta, attachment pagination, removal and expired-token recovery")
if __name__=="__main__":
    run();envelope();surrogate_mail();upgrade();graph_rounds()
