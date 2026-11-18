import json
import re
import sqlite3
import time
from re import _constants as op, _parser
import regex
from indexdb import terms, unpack_body

MODES = {"subject": ("subject",), "subject_body": ("subject", "body"),
         "all": ("subject", "body", "attachment"), "attachment": ("attachment",)}
SAFE_RUN = re.compile(r"[a-zA-Z0-9 _./:@#%+=,\u3400-\u9fff-]+")
# Only plan the common subset for which Python re and regex VERSION0 agree.
UNSUPPORTED = re.compile(r"\(\?(?!:)|\(\*|\\(?![dDsSwWbBAZntfr\\.^$|?*+()[\]{}\-/])|\[\[|&&|~~|--|\|\|")

def literal_clause(run):
    choices = [terms(s) for s in SAFE_RUN.findall(run)]
    best = max(choices, key=len, default="")
    if len(best) < 3:
        return ""
    end = len(best) - 3
    grams = dict.fromkeys(best[i:i+3] for i in (0, end // 3, end * 2 // 3, end))
    return "(" + " AND ".join('"' + g + '"' for g in grams) + ")"

def candidates(pattern):
    if UNSUPPORTED.search(pattern) or re.search(r"(?<!\\)\{(?![0-9]+(?:,[0-9]*)?\})", pattern):
        return ""
    try:
        tree = _parser.parse(pattern, 0)
    except (re.error, OverflowError, RecursionError):
        return ""

    def sequence(nodes):
        clauses, run = [], []
        def flush():
            if run:
                clause = literal_clause("".join(run))
                if clause:
                    clauses.append(clause)
                run.clear()
        for kind, value in nodes:
            if kind is op.LITERAL:
                run.append(chr(value))
                continue
            flush()
            child = ""
            if kind is op.SUBPATTERN:
                child = sequence(value[-1])
            elif kind in (op.MIN_REPEAT, op.MAX_REPEAT, op.POSSESSIVE_REPEAT) and value[0] > 0:
                child = sequence(value[2])
            elif kind is op.BRANCH:
                options = [sequence(branch) for branch in value[1]]
                if all(options):
                    child = "(" + " OR ".join(options) + ")"
            if child:
                clauses.append(child)
        flush()
        return "(" + " AND ".join(clauses[:6]) + ")" if clauses else ""
    result = sequence(tree)
    return result if len(result) < 1800 else ""

def search(db, args, cfg, cancel=lambda:False, force_scan=False):
    start = time.perf_counter()
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= 2048:
        raise ValueError("请输入 1 至 2048 个字符的正则表达式。")
    fields = MODES.get(args.get("mode", cfg["mode"]))
    if not fields:
        raise ValueError("未知搜索范围。")
    compiled = regex.compile(pattern, regex.VERSION0 | (0 if args.get("caseSensitive", cfg["caseSensitive"]) else regex.IGNORECASE))
    limit = max(1, min(int(args.get("limit", cfg["limit"])), 1000))
    clause = "" if force_scan else candidates(pattern)
    where, params = [], []
    if clause:
        where.append("m.id IN (SELECT rowid FROM grams WHERE grams MATCH ?)")
        params.append("{" + " ".join(fields) + "} : " + clause)
    if args.get("folder"):
        where.append("m.folder=?")
        params.append(args["folder"])
    cursor = args.get("cursor")
    if cursor:
        where.append("(m.received,m.id)<(?,?)")
        params.extend([cursor[0], int(cursor[1])])
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    columns = "m.id,m.subject,m.sender,m.received,m.folder"
    if "body" in fields:
        columns += ",m.body"
    if "attachment" in fields:
        columns += ",m.attachments"
    sql = "SELECT " + columns + " FROM mail m" + where_sql + " ORDER BY m.received DESC,m.id DESC"
    items, scanned, reason, next_page = [], 0, "", None
    deadline = time.monotonic() + 25
    def stopped():
        return cancel() or time.monotonic() >= deadline
    db.set_progress_handler(lambda: int(stopped()), 2000)
    try:
        for row in db.execute(sql, params):
            if stopped():
                reason = "已取消" if cancel() else "已达到查询时间上限"
                break
            scanned += 1
            for field in fields:
                if field == "subject":
                    values = (row["subject"],)
                elif field == "body":
                    values = (unpack_body(row["body"]),)
                else:
                    values = json.loads(row["attachments"])
                found = False
                for value in values:
                    match = compiled.search(value, timeout=cfg["timeoutMs"] / 1000)
                    if match is None:
                        continue
                    if len(items) == limit:
                        next_page = [items[-1]["received"], items[-1]["id"]]
                    else:
                        excerpt = value[max(0, match.start()-32):match.start()+100].replace("\n", " ").replace("\r", " ")
                        items.append({k:row[k] for k in ("id","subject","sender","received","folder")} |
                                     {"field":field, "snippet":excerpt})
                    found = True
                    break
                if found:
                    break
            if next_page:
                break
    except TimeoutError:
        reason = "单封邮件的正则匹配超时，请缩小范围或简化表达式"
    except sqlite3.OperationalError:
        if not stopped():
            raise
        reason = "已取消" if cancel() else "已达到查询时间上限"
    finally:
        db.set_progress_handler(None, 0)
    return {"items":items, "next":next_page, "partial":reason, "candidatesChecked":scanned,
            "strategy":"trigram" if clause else "scan", "ms":round((time.perf_counter()-start)*1000,1)}
