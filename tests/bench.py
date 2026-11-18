"""Reproducible whole-index benchmark. All records are synthetic."""
import argparse
import ctypes
import json
import random
import statistics
import sys
import time
from pathlib import Path
from ctypes import wintypes

from config import DEFAULTS
from indexdb import connect,save
from search import search

def peak_mib():
    class Counters(ctypes.Structure):
        _fields_=[("cb",wintypes.DWORD),("faults",wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in
            ("peak","working","pp","p","npp","np","page","peakpage")]
    c=Counters()
    c.cb=ctypes.sizeof(c)
    ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
    get=ctypes.windll.psapi.GetProcessMemoryInfo
    get.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not get(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(c),c.cb):
        raise ctypes.WinError()
    return round(c.peak/1048576,1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("db",type=Path); ap.add_argument("--count",type=int,default=50000)
    arg=ap.parse_args()
    if arg.db.exists():
        raise SystemExit("Specify a new benchmark database.")
    db=connect(arg.db); rand=random.Random(788); start=time.perf_counter(); originals=0
    words=("预算 货运 调整 已确认 合同 草案 入库 清单 到期 回执 审核 review budget shipping confirmed "
           "purchase revision statement forecast settlement reference payment response received").split()
    for i in range(arg.count):
        # Unique order numbers, amounts, letter strings and variable-length bilingual paragraphs.
        chunks=[]
        for _ in range(rand.randint(5,15)):
            chunks.append(" ".join(rand.choices(words,k=12))+" %08x %.2f"%(rand.getrandbits(32),rand.random()*90000))
        body="\n".join(chunks)
        if i%4093==0: body+="\n晨星计划 RAVEN-%04d" % (i%997)
        originals+=len(body.encode())
        item=dict(store="bench",entry=str(i),folder="/bench/"+str(i%9),folder_id=str(i%9),stamp="1",
                  subject="项目 %s / PO-%06d"%(words[i%len(words)],i),sender="Fixture "+str(i%71),
                  received="2026-07-%02dT%02d:%02d:00Z"%(i%28+1,i%24,i%60),body=body,
                  attachments=["季度汇总-%06d.xlsx"%i] if i%4==0 else [])
        save(db,item)
        if (i+1)%128==0: db.commit()
    db.commit(); db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.close()
    built=round(time.perf_counter()-start,2)
    db=connect(arg.db)
    cases=[("subject",r"PO-04999\d"),("subject_body",r"晨星计划\s+RAVEN-\d+"),("all",r"季度汇总-0499\d{2}\.xlsx"),
           ("subject_body","晨星"),("subject",r"(?<=PO-)04999\d")]
    cases_out=[]
    for mode,pattern in cases:
        args={"mode":mode,"pattern":pattern,"limit":200}
        cold=search(db,args,DEFAULTS)
        values=[search(db,args,DEFAULTS)["ms"] for _ in range(15)]
        brute=search(db,args,DEFAULTS,force_scan=True)
        assert [i["id"] for i in cold["items"]]==[i["id"] for i in brute["items"]]
        assert not cold["partial"] and not brute["partial"]
        cases_out.append(dict(mode=mode,pattern=pattern,strategy=cold["strategy"],matches=len(cold["items"]),
            checked=cold["candidatesChecked"],firstMs=cold["ms"],medianMs=statistics.median(values),
            p95Ms=sorted(values)[14],scanMs=brute["ms"]))
    print(json.dumps(dict(records=arg.count,bodyMiB=round(originals/1048576,1),buildSeconds=built,
        databaseMiB=round(arg.db.stat().st_size/1048576,1),peakWorkingSetMiB=peak_mib(),cases=cases_out),ensure_ascii=True,indent=2))
if __name__=="__main__":
    main()
