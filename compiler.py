"""Guideline Compiler: turn a notice's proposal-format clauses into a machine-checkable checklist."""
import re
from dataclasses import dataclass

@dataclass
class Item:
    name: str
    limit: int = 0
    unit: str = ""      # chars | words | items | ""
    kind: str = "section"   # section | attachment

def compile_checklist(notice):
    items = []
    for line in notice.proposal_format:
        m = re.match(r"^(.*?)\s*\[max (\d+) (chars|words|items)\]\s*$", line)
        if m:
            items.append(Item(m.group(1).strip(), int(m.group(2)), m.group(3)))
        else:
            items.append(Item(line.strip()))
    for a in notice.attachments:
        items.append(Item(a.strip(), kind="attachment"))
    return items

def show(items):
    out = []
    for i, it in enumerate(items, 1):
        lim = f" (max {it.limit} {it.unit})" if it.limit else ""
        out.append(f"{i:2}. [{it.kind[:4]}] {it.name}{lim}")
    return "\n".join(out)
