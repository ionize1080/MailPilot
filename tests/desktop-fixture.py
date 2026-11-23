"""A reproducible, isolated mailbox for the Electron reader and search UI."""
import base64
import contextlib
import os
import sys
from pathlib import Path
from config import db_path, settings
from indexdb import connect, save

cfg = settings()
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview_fixtures import create
files_dir = Path(os.environ["MAILPILOT_HOME"]) / "originals"
create(files_dir)
assert os.environ.get("MAILPILOT_HOME") and not cfg["autoRefresh"]
assert db_path(cfg).is_relative_to(Path(os.environ["MAILPILOT_HOME"]).resolve())
with contextlib.closing(connect(db_path(cfg))) as db, db:
    for i, (subject, sender, address) in enumerate([
        ("十一月采购订单确认 · PO-104826","林婉宁","wanning@example.com"),
        ("交货时间与费用明细 · PO-104812","陈明哲","mingzhe@example.com"),
        ("请核对本月采购清单","采购组","purchasing@example.com")]):
        attachment = f"报价单-PO-{104826-i:06}.xlsx"
        text = "各位好，\n请核对采购订单 PO-104826 的交付信息。\n物料\t数量\n办公耗材\t24\n谢谢！"
        html = """<html><head><style>td,th{padding:8px 18px;border:1px solid #c7d9d0}th{background:#dfede6}</style></head>
        <body style="font:15px Calibri,'Microsoft YaHei UI',sans-serif;color:#23463a"><p>各位好，</p>
        <p>请核对采购订单 <b>PO-</b><em>104826</em> 的交付信息。</p><table style="border-collapse:collapse">
        <tr><th>物料</th><th>数量</th></tr><tr><td>办公耗材</td><td>24</td></tr></table>
        <p>谢谢！</p><img width="16" height="16" src="cid:signature" alt="签名"><img src="https://example.invalid/mail.png" alt="外部图片"></body></html>"""
        if i==2:
            tail="完整邮件内容与交付记录。"*700+"尾码-9823"
            text+="\n"+tail
            html=html.replace("</body>","<p>"+tail+"</p></body>")
        inline = "data:image/png;base64," + base64.b64encode((Path(__file__).resolve().parents[1]/"docs/icon-16.png").read_bytes()).decode()
        meta = {"sender":[f"{sender} <{address}>"], "to":["运营组 <ops@example.com>"],
                "cc":["陈予 <review@example.org>"],"bcc":["归档 <archive@example.org>"],
                "sent":["2026-11-17T02:00:00Z"],"importance":["高"],"categories":["采购"],
                "headers":["Message-ID: <aurora.qa@example.org>\r\nX-Review: 📨audit-only"],
                "files":[{"name":attachment,"size":29644,"type":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}]}
        names = [attachment]
        (files_dir/attachment).write_bytes((files_dir/"报价单.xlsx").read_bytes())
        if i == 0:
            names += ["确认书.pdf", "交付说明.docx", "进度汇报.pptx", "记录.md", "说明.txt", "签名.png", "数据.csv", "收货照片", "缩略图.webp"]
            names.extend(p.name for p in files_dir.iterdir() if p.suffix in (".doc",".xls",".ppt"))
        meta["files"] = [dict(name=name,size=(files_dir/name).stat().st_size,
                              type="image/jpeg" if name == "收货照片" else "") for name in names]
        save(db, dict(store="qa",entry=str(i),folder="收件箱 / 采购",folder_id="purchase",stamp="1",subject=subject,
             sender=sender,received=f"2026-11-{18-i}T01:16:00Z",body=text,html=html,inlineImages={"signature":inline},
             metadata=meta,attachments=names))
    for i in range(65):
        save(db, dict(store="qa", entry=f"sidebar-{i}", folder="Sidebar", folder_id="sidebar", stamp="1",
                      subject=f"Sidebar QA {i:02d}", sender="QA", received="2026-11-01T00:00:00Z",
                      body="", attachments=[]))
