"""Ingestion: parse notice files into structured records and section chunks."""
import re, datetime as dt
from pathlib import Path
from dataclasses import dataclass, field

LIST_KEYS = {"Eligibility", "Proposal format", "Attachments"}
SCALAR_KEYS = ["ID", "Title", "Agency", "Source", "Retrieved", "Note",
               "Deadline", "Budget", "Duration", "Themes"]

@dataclass
class Notice:
    id: str
    title: str
    agency: str
    source: str
    note: str = ""
    deadline: str = ""          # ISO date or ""
    deadline_text: str = ""
    budget: str = ""
    duration: str = ""
    themes: str = ""
    eligibility: list = field(default_factory=list)
    proposal_format: list = field(default_factory=list)
    attachments: list = field(default_factory=list)

    def deadline_date(self):
        try:
            return dt.date.fromisoformat(self.deadline)
        except ValueError:
            return None

    def status(self, today):
        d = self.deadline_date()
        if d is None:
            return "no fixed deadline on page"
        return "OPEN" if d >= today else "EXPIRED"

def parse_notice(text: str) -> Notice:
    data, cur = {}, None
    for line in text.splitlines():
        if line.startswith("- ") and cur in LIST_KEYS:
            data[cur].append(line[2:].strip())
            continue
        m = re.match(r"^([A-Za-z ]+):\s*(.*)$", line)
        if m and (m.group(1) in SCALAR_KEYS or m.group(1) in LIST_KEYS):
            cur = m.group(1)
            data[cur] = [] if cur in LIST_KEYS else m.group(2).strip()
    dl = data.get("Deadline", "")
    iso = dl if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl) else ""
    return Notice(id=data["ID"], title=data["Title"], agency=data["Agency"],
                  source=data["Source"], note=data.get("Note", ""),
                  deadline=iso, deadline_text=dl, budget=data.get("Budget", ""),
                  duration=data.get("Duration", ""), themes=data.get("Themes", ""),
                  eligibility=data.get("Eligibility", []),
                  proposal_format=data.get("Proposal format", []),
                  attachments=data.get("Attachments", []))

def load_notices(folder="data/notices"):
    base = Path(__file__).parent / folder
    return [parse_notice(p.read_text()) for p in sorted(base.glob("*.txt"))]

def chunk(notice: Notice):
    """Section-level chunks, each tagged with notice id (keeps metadata for filtering)."""
    parts = [("overview", f"{notice.title}. {notice.agency}. {notice.themes}"),
             ("funding", f"Budget {notice.budget}. Duration {notice.duration}. Deadline {notice.deadline_text}.")]
    if notice.eligibility:
        parts.append(("eligibility", " ".join(notice.eligibility)))
    if notice.proposal_format:
        parts.append(("format", " ".join(notice.proposal_format)))
    return [{"notice_id": notice.id, "section": s, "text": t} for s, t in parts]

if __name__ == "__main__":
    ns = load_notices()
    total = sum(len(chunk(n)) for n in ns)
    print(f"Parsed {len(ns)} notices -> {total} chunks")
    for n in ns:
        print(f"  {n.id:16} deadline={n.deadline_text:28} elig={len(n.eligibility)} sections={len(n.proposal_format)}")
