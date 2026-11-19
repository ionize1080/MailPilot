"""Index an isolated test PST using the real Outlook Object Model."""
import contextlib
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
import pythoncom
from win32com.client import dynamic
from config import settings,db_path
from indexdb import connect, set_state
from outlook import sync
from search import search

def main():
    cfg=settings()
    assert os.environ.get("MAILPILOT_HOME"), "Use an isolated test profile"
    home=Path(os.environ["MAILPILOT_HOME"]);home.mkdir(parents=True,exist_ok=True)
    assert db_path(cfg).is_relative_to(home.resolve()) and not cfg["autoRefresh"], "Use a fixture-only index and disable auto refresh"
    pst=home/("test-"+uuid.uuid4().hex+".pst")
    app=dynamic.Dispatch("Outlook.Application");ns=app.GetNamespace("MAPI")
    ns.AddStoreEx(str(pst),3)
    root=explorer=None
    try:
        stores=ns.Stores
        store=next(s for s in (stores.Item(i) for i in range(1,stores.Count+1)) if os.path.normcase(s.FilePath)==os.path.normcase(str(pst)))
        root=store.GetRootFolder(); folder=root.Folders.Add("MailPilot QA",6)
        explorer=folder.GetExplorer(0);explorer.Display()
        file=home/"Aurora-QA-741.pdf";file.write_bytes(b"MailPilot synthetic filename fixture")
        unicode_body = "x" * 217 + "\udd00Unicode-tail 📨"
        for title,body,attached in [("Pilot-INV-7701",unicode_body,False),("Control","MORNING-9825",False),
                                     ("Attachment receipt","Proof code: JADE-8317",True)]:
            item=folder.Items.Add("IPM.Note");item.Subject=title
            if title=="Control":
                item.BodyFormat=3
            item.Body=body
            if attached:
                item.Attachments.Add(str(file))
                item.HTMLBody="<html><body><p>Proof code: <b>JADE-8317</b></p><table><tr><td>Delivery</td></tr></table></body></html>"
                item.CC="archive@example.org"
                item.Categories="Fixture-QA"
            item.Save()
            if item.Parent.EntryID != folder.EntryID:
                item=item.Move(folder)
            assert item.Parent.EntryID==folder.EntryID
        deadline=time.monotonic()+10
        while folder.GetTable().GetRowCount()<3 and time.monotonic()<deadline:
            pythoncom.PumpWaitingMessages();time.sleep(.1)
        time.sleep(2.1)
        with contextlib.closing(connect(db_path(cfg))) as db:
            run=lambda:sync(db,cfg,lambda *v:None,lambda:False,[store])
            first=run(); assert first["changed"]==3 and first["errors"]==0, first
            for pattern,mode,want in [("MORNING-9825","subject",0),("MORNING-9825","subject_body",1),
                                      ("Aurora-QA","subject_body",0),(r"Aurora-QA-\d+\.pdf","all",1),
                                      (r"INV-\d{4}","subject",1)]:
                r=search(db,dict(pattern=pattern,mode=mode),cfg);assert len(r["items"])==want,(pattern,r)
            second=run();assert second["changed"]==0,second
            from service import read_mail, dispatch
            unicode_hit = search(db,dict(pattern="Unicode-tail 📨",mode="subject_body"),cfg)["items"]
            assert len(unicode_hit)==1 and unicode_hit[0]["field"]=="body"
            indexed_body = read_mail(db,dict(id=unicode_hit[0]["id"]))["body"]
            source_body = folder.Items.Find("[Subject] = 'Pilot-INV-7701'").Body
            assert indexed_body == source_body.replace("\udd00", "\ufffd")
            rtf_id=search(db,dict(pattern="MORNING-9825",mode="all"),cfg)["items"][0]["id"]
            rendered=dispatch("detail",dict(id=rtf_id,pattern="MORNING",mode="full"),cfg,None)
            assert rendered["html"] and "MORNING" in rendered["html"], "RTF detail is missing"
            time.sleep(1.1)  # PST table timestamps have one-second granularity.
            item=folder.Items.Find("[Subject] = 'Control'"); item.Body=item.Body+"\nDelta marker at 18:30";item.Save()
            third=run();assert third["changed"]==1,third
            assert len(search(db,dict(pattern="Delta marker",mode="subject_body"),cfg)["items"])==1
            # Read through a real result ID, without marking a personal mail as read.
            rid=search(db,dict(pattern="Aurora-QA",mode="attachment"),cfg)["items"][0]["id"]
            assert "JADE-8317" in read_mail(db,dict(id=rid))["body"]
            rich = dispatch("detail",dict(id=rid,pattern="archive",mode="full"),cfg,None)
            assert "<table" in rich["html"].lower() and rich["marks"]["cc"], rich["fields"].keys()
            hit = search(db,dict(pattern="Aurora-QA",mode="attachment"),cfg)["items"][0]
            transfer = dict(id=rid,key=hit["key"],stamp=rich["stamp"],action="save")
            downloaded = home/"原件另存为.pdf"
            assert dispatch("attachment_transfer",transfer|dict(index=0,destination=str(downloaded)),cfg,None)["count"]==1
            assert downloaded.read_bytes()==file.read_bytes()
            target = home/"全部附件"
            target.mkdir()
            (target/file.name).write_bytes(b"keep")
            assert dispatch("attachment_transfer",transfer|dict(index=None,destination=str(target)),cfg,None)=={"count":1,"errors":[]}
            assert (target/file.name).read_bytes()==b"keep"
            assert (target/(file.stem+" (2).pdf")).read_bytes()==file.read_bytes()
            assert search(db,dict(pattern="Fixture-QA",mode="full"),cfg)["items"]
            set_state(db,"lastSync",int(time.time()))
            print(json.dumps(dict(outlook=app.Version,initial=first,unchanged=second,modified=third,scopeCases=5),indent=2))
    finally:
        if root is not None: ns.RemoveStore(root)
        if explorer is not None:
            try: explorer.Close()
            except Exception: pass
if __name__=="__main__":
    main()
