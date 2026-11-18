import json
import re
import sqlite3
import time
from re import _constants as op, _parser
import regex
from indexdb import terms, unpack_body, mail_key
from message import message_fields

MODES = {"subject": ("subject",), "subject_body": ("subject", "body"),
         "all": ("subject", "body", "attachment"), "attachment": ("attachment",),
         "sender": ("sender", "onBehalf"), "full": ("subject", "sender", "onBehalf", "to", "cc", "bcc",
                                                   "body", "attachment", "*")}
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

def query(args, cfg):
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= 2048:
        raise ValueError("请输入 1 至 2048 个字符的正则表达式。")
    fields = MODES.get(args.get("mode", cfg["mode"]))
    if not fields:
        raise ValueError("未知搜索范围。")
    compiled = regex.compile(pattern, regex.VERSION0 | (0 if args.get("caseSensitive", cfg["caseSensitive"]) else regex.IGNORECASE))
    return fields, compiled


def utf16(text):
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def subjects(key, value):
    yield value, 0
    if key in ("sender","onBehalf","to","cc","bcc","replyTo"):
        address = re.fullmatch(r"(.+) <([^<>]+)>", value, re.DOTALL)
        if address:
            for i in (1,2):
                yield address[i], address.start(i)


def first_span(compiled, key, value, timeout):
    for text, offset in subjects(key, value):
        match = compiled.search(text, timeout=timeout)
        if match is not None:
            return match.start()+offset, match.end()+offset


def match_ranges(compiled, value, timeout, remaining):
    """DOM text offsets use UTF-16. Convert incrementally, including empty matches."""
    ranges, last, offset = [], 0, 0
    for match in compiled.finditer(value, timeout=timeout):
        if len(ranges) == remaining:
            return ranges, True
        start, end = match.span()
        offset += utf16(value[last:start])
        size = utf16(value[start:end])
        ranges.append([offset, offset+size])
        last, offset = end, offset+size
    return ranges, False


def selected_fields(fields, available):
    keys = [k for k in fields if k in available]
    if "*" in fields:
        keys.extend(k for k in available if k not in keys)
    return keys


def highlights(fields, compiled, available, cfg):
    marks, remaining, partial = {}, 3000, ""
    try:
        for key in selected_fields(fields, available):
            groups = []
            for value in available[key]:
                spans = []
                for text, offset in subjects(key,value):
                    part, overflow = match_ranges(compiled, text, cfg["timeoutMs"]/1000, remaining-len(spans))
                    base = utf16(value[:offset])
                    spans.extend((a+base,b+base) for a,b in part)
                    if overflow or (text == value and spans):
                        break
                groups.append(spans)
                remaining -= len(spans)
                if overflow:
                    partial = "已标出前 3,000 处匹配"
                    break
            if any(groups):
                marks[key] = groups
            if partial:
                break
    except TimeoutError:
        partial = "高亮匹配超时，可缩小表达式范围"
    return {"marks": marks, "partial": partial}


def search(db, args, cfg, cancel=lambda:False, force_scan=False):
    start = time.perf_counter()
    fields, compiled = query(args, cfg)
    limit = max(1, min(int(args.get("limit", cfg["limit"])), 1000))
    clause = "" if force_scan else candidates(args["pattern"])
    where, params = [], []
    if clause:
        branches = []
        content = [f for f in fields if f in ("subject", "body", "attachment")]
        if content:
            branches.append("SELECT rowid FROM grams WHERE grams MATCH ?")
            params.append("{" + " ".join(content) + "} : " + clause)
        if "sender" in fields:
            branches.append("SELECT rowid FROM envelope WHERE envelope MATCH ?")
            params.append(clause if "*" in fields else "sender : " + clause)
        where.append("m.id IN (" + " UNION ALL ".join(branches) + ")")
    if args.get("folder"):
        where.append("m.folder=?")
        params.append(args["folder"])
    cursor = args.get("cursor")
    if cursor:
        where.append("(m.received,m.id)<(?,?)")
        params.extend([cursor[0], int(cursor[1])])
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    columns = "m.id,m.subject,m.sender,m.received,m.folder,m.store,m.entry"
    if "body" in fields:
        columns += ",m.body"
    if "attachment" in fields:
        columns += ",m.attachments"
    if "sender" in fields:
        columns += ",m.metadata"
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
            names = json.loads(row["attachments"]) if "attachment" in fields else []
            available = {"subject": [row["subject"]], "attachment": names}
            if "sender" in fields:
                available = message_fields(row["subject"], row["sender"], row["received"], row["folder"],
                                           names, json.loads(row["metadata"]))
            if "body" in fields:
                available["body"] = None  # Inflate only if earlier fields did not match.
            for field in selected_fields(fields, available):
                values = (unpack_body(row["body"]),) if field == "body" else available[field]
                found = False
                for value in values:
                    position = first_span(compiled, field, value, cfg["timeoutMs"] / 1000)
                    if position is None:
                        continue
                    if len(items) == limit:
                        next_page = [items[-1]["received"], items[-1]["id"]]
                    else:
                        begin, end = position
                        left, right = max(0, begin-32), begin+100
                        excerpt = value[left:right].replace("\n", " ").replace("\r", " ")
                        items.append({k:row[k] for k in ("id","subject","sender","received","folder")} |
                                     {"field":field, "snippet":excerpt, "key":mail_key(row["store"], row["entry"]),
                                      "span":[utf16(value[left:begin]), utf16(value[left:min(end,right)])]})
                        if field in ("subject", "sender"):
                            items[-1]["fieldSpan"] = [utf16(value[:begin]), utf16(value[:end])]
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
