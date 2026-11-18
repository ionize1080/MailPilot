"""The searchable and readable representations of the same message fields."""
from html.parser import HTMLParser
import re


def person(name="", address=""):
    name, address = (str(v or "").strip() for v in (name, address))
    return f"{name} <{address}>" if name and address and name.casefold() != address.casefold() else name or address


def values(*items):
    return list(dict.fromkeys(str(v) for v in items if v is not None and str(v).strip()))


def message_fields(subject, sender, received, folder, attachments, meta):
    fields = {"subject": [subject], "sender": meta.get("sender") or values(sender),
              "attachment": attachments, "received": values(received), "folder": values(folder)}
    for key, items in meta.items():
        if key not in ("sender", "files") and items:
            fields[key] = items
    for key, prop in (("attachmentType", "type"), ("attachmentSize", "size"),
                      ("contentId", "cid"), ("attachmentLocation", "location")):
        items = values(*(f.get(prop) for f in meta.get("files", [])))
        if items:
            fields[key] = items
    return fields


class BodyText(HTMLParser):
    blocks = set("p div li tr h1 h2 h3 h4 h5 h6 blockquote pre section article hr table".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
        self.links = {}
        self.alternatives = {}

    def newline(self):
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def parse_marked_section(self, i, report=1):
        # Office and third-party senders also emit proprietary marked sections.
        try:
            return super().parse_marked_section(i, report)
        except AssertionError:
            end = self.rawdata.find(">", i+3)
            return end+1 if end >= 0 else -1

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "a" and re.match(r"^(?:https?:|mailto:|tel:)", attr.get("href") or "", re.I):
            self.links[attr["href"]] = None
        if tag == "img" and attr.get("alt"):
            self.alternatives[attr["alt"]] = None
        if tag in ("head", "style", "script", "title"):
            self.hidden += 1
        elif not self.hidden:
            if tag == "br":
                self.parts.append("\n")
            elif tag in self.blocks:
                self.newline()

    def handle_endtag(self, tag):
        if tag in ("head", "style", "script", "title"):
            self.hidden = max(0, self.hidden-1)
        elif not self.hidden:
            if tag in self.blocks:
                self.newline()
            elif tag in ("td", "th"):
                self.parts.append("\t")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(html):
    parser = BodyText()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts).strip("\n")
