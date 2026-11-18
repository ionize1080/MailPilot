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
        for title,body,attached in [("Pilot-INV-7701","ordinary",False),("Control","MORNING-9825",False),
                                     ("Attachment receipt","Proof code: JADE-8317",True)]:
            item=folder.Items.Add("IPM.Note");item.Subject=title;item.Body=body
            if attached:item.Attachments.Add(str(file))
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
            time.sleep(1.1)  # PST table timestamps have one-second granularity.
            item=folder.Items.Item(1); item.Body=item.Body+"\nDelta marker at 18:30";item.Save()
            third=run();assert third["changed"]==1,third
            assert len(search(db,dict(pattern="Delta marker",mode="subject_body"),cfg)["items"])==1
            # Read through a real result ID, without marking a personal mail as read.
            rid=search(db,dict(pattern="Aurora-QA",mode="attachment"),cfg)["items"][0]["id"]
            from service import read_mail
            assert "JADE-8317" in read_mail(db,dict(id=rid))["body"]
            set_state(db,"lastSync",int(time.time()))
            print(json.dumps(dict(outlook=app.Version,initial=first,unchanged=second,modified=third,scopeCases=5),indent=2))
    finally:
        if root is not None: ns.RemoveStore(root)
        if explorer is not None:
            try: explorer.Close()
            except Exception: pass
if __name__=="__main__":
    main()
