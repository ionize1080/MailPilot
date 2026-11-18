import contextlib
import random
import tempfile
import urllib.error
from pathlib import Path
from config import DEFAULTS
from graph import API, sync_pages
from indexdb import connect,save
from search import search

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
            for mode in ("all","subject","subject_body","attachment"):
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

def graph_rounds():
    f=API+"/me/mailFolders?$select=id,displayName,childFolderCount"
    delta=API+"/me/mailFolders/F/messages/delta?$select=id,changeKey"
    token=API+"/delta/1";next_token=API+"/delta/2"
    cfg=DEFAULTS|{"pauseMs":0}
    with tempfile.TemporaryDirectory() as tmp, contextlib.closing(connect(Path(tmp)/"m.db")) as db:
        deleted=False;expired=False;pages=[]
        def fetch(url):
            pages.append(url)
            if url==f:return {"value":[dict(id="F",displayName="Inbox",childFolderCount=0)]}
            if url==delta:return {"value":[{"id":"A"}] if not expired else [],"@odata.nextLink":API+"/page2"}
            if url==API+"/page2":return {"value":[],"@odata.deltaLink":token}
            if url in (token,next_token):
                if expired:raise urllib.error.HTTPError(url,410,"Gone",{},None)
                return {"value":[{"id":"A","@removed":{}}] if deleted else [],"@odata.deltaLink":next_token}
            if "/me/messages/A?" in url:return dict(id="A",subject="Graph message",changeKey="01",body={"content":"fixture"},
                attachments=[{"name":"Page1.xlsx"}],parentFolderId="F",**{"attachments@odata.nextLink":API+"/attach2"})
            if url==API+"/attach2":return {"value":[{"name":"Second.csv"}]}
            raise AssertionError(url)
        def run():return sync_pages(db,cfg,lambda *args:None,fetch,"fixture")
        assert run()["changed"]==1
        assert search(db,dict(pattern=r"Second\.csv",mode="attachment"),DEFAULTS)["items"]
        assert run()["changed"]==0 and pages.count(delta)==1
        deleted=True
        assert run()["removed"]==1
        with db:save(db,row(3,"old")|{"store":"fixture","folder_id":"F"})
        expired=True
        assert run()["removed"]==1 and db.execute("SELECT count(*) FROM mail").fetchone()[0]==0
        print("PASS Graph folder, delta, attachment pagination, removal and expired-token recovery")
if __name__=="__main__":
    run();graph_rounds()
