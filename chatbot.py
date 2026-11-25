"""Grounded Q&A assistant. Answers only from the call records (no LLM needed); every answer cites its source.
If the records do not contain the answer it says so and shows the closest record instead of guessing."""
import re, datetime as dt
from eligibility import check

ALIASES = {
    "SERB-SRG": ["srg", "start-up research grant", "startup research grant", "start up research"],
    "SERB-ECRA": ["ecra", "early career research award", "early career"],
    "SERB-CRG": ["crg", "core research grant", "core research"],
    "DBT-MICROBIOME": ["microbiome"],
    "DBT-BIOCARE": ["biocare", "bio care"],
    "ICMR-NMC-MEDEDU": ["nmc", "medical education"],
    "ICMR-FIW-2026": ["first in the world", "fiw", "first in world"],
    "DHR-NER-HRD": ["dhr", "north east", "northeast", "north eastern", "ner "],
}
SUGGESTIONS = ["Which calls are open right now?", "Which call should I apply to?", "What is the deadline for the ICMR First in the World call?",
               "What documents do I need for the SERB Start-up Research Grant?", "Am I eligible for the SERB Early Career Research Award?",
               "Compare SRG and ECRA", "How much funding does the First in the World challenge give?"]

def _calls_in(q, idx):
    ql = " " + q.lower() + " "
    found = [i for i, al in ALIASES.items() if any(a in ql for a in al)]
    if not found:
        r = idx.search(q, today=dt.date(2000, 1, 1), include_expired=True, top_k=1)
        if r and r[0]["score"] >= 0.25: found = [r[0]["notice"].id]
    return found

def _src(n): return f"\n\n*Source: [{n.agency}]({n.source}). Records are paraphrased; verify on the official page.*"

def _days(n, today):
    d = n.deadline_date()
    if d is None: return "no fixed deadline stated"
    k = (d - today).days
    return f"{d:%d %b %Y} ({k} days left)" if k >= 0 else f"{d:%d %b %Y} (closed {-k} days ago)"

def answer(q, idx, profile, today):
    ql = q.lower().strip()
    if not ql:
        return {"text": "Ask me about deadlines, budgets, eligibility, documents or required sections.", "intent": "empty", "sources": []}
    if re.search(r"\b(hi|hello|hey|help|what can you do)\b", ql) and len(ql.split()) <= 6:
        return {"text": "I can answer from the 8 funding-call records: **deadlines, budgets, durations, eligibility for you, required documents, proposal sections, and comparisons**. Try one of the suggested questions.", "intent": "help", "sources": []}
    ids = _calls_in(q, idx)
    # compare
    if "compare" in ql or " vs " in ql or "difference" in ql:
        if len(ids) >= 2:
            ns = [idx.by_id[i] for i in ids[:3]]
            rows = ["| | " + " | ".join(n.id for n in ns) + " |", "|---|" + "---|" * len(ns)]
            rows.append("| Deadline | " + " | ".join(_days(n, today) for n in ns) + " |")
            rows.append("| Budget | " + " | ".join(n.budget[:70] for n in ns) + " |")
            rows.append("| Duration | " + " | ".join(n.duration for n in ns) + " |")
            rows.append("| Your verdict | " + " | ".join(check(n, profile, today)["verdict"].split(" (")[0] for n in ns) + " |")
            return {"text": "\n".join(rows) + "\n\n*Sources: " + ", ".join(f"[{n.id}]({n.source})" for n in ns) + "*", "intent": "compare", "sources": [n.id for n in ns]}
        return {"text": "Tell me which two calls to compare, for example *Compare SRG and ECRA*.", "intent": "compare", "sources": []}
    # open calls / closing soon
    if re.search(r"\b(open|closing|active|available|current)\b", ql) and not ids:
        rows = [(n, n.deadline_date()) for n in idx.notices if n.status(today) in ("OPEN", "no fixed deadline on page")]
        rows.sort(key=lambda t: (t[1] is None, t[1] or dt.date.max))
        lines = [f"- **{n.title}**: {_days(n, today)}" for n, _ in rows]
        return {"text": f"Calls not yet closed as of {today:%d %b %Y}:\n\n" + "\n".join(lines) + "\n\nCalls with no stated deadline publish dates per call on the agency portal.", "intent": "open", "sources": [n.id for n, _ in rows]}
    # recommend
    if (re.search(r"\b(recommend|which call|best call|should i apply|where should i)\b", ql) or re.search(r"\b(am i|can i|do i)\b.*\b(eligible|qualify|apply)\b|\b(eligible|eligibility|qualify)\b", ql)) and not ids:
        res = [check(n, profile, today) for n in idx.notices]
        good = [r for r in res if r["verdict"].startswith("ELIGIBLE")]
        near = [r for r in res if r["verdict"].startswith("NEAR")]
        t = "Based on your sidebar profile:\n\n"
        t += "**Eligible now:**\n" + ("\n".join(f"- {r['notice'].title} ({_days(r['notice'], today)})" for r in good) or "- none") + "\n\n"
        t += "**One step away:**\n" + ("\n".join(f"- {r['notice'].title}: {r['blockers'][0].why}" for r in near) or "- none")
        return {"text": t, "intent": "recommend", "sources": [r["notice"].id for r in good + near]}
    if ids:
        n = idx.by_id[ids[0]]
        if re.search(r"\b(eligible|eligibility|qualify|can i|am i|why|who can)\b", ql):
            res = check(n, profile, today)
            lines = [f"**{n.title}: {res['verdict']}**", ""]
            for r in res["results"]:
                lines.append(f"- {'✅' if r.status == 'PASS' else '❌' if r.status == 'FAIL' else '🔍'} {r.clause}: *{r.why}*")
            return {"text": "\n".join(lines) + _src(n), "intent": "eligibility", "sources": [n.id]}
        if re.search(r"\b(deadline|last date|when|due|close|closing)\b", ql):
            return {"text": f"**{n.title}** deadline: {_days(n, today)}." + _src(n), "intent": "deadline", "sources": [n.id]}
        if re.search(r"\b(budget|funding|how much|amount|money|grant size|cost|lakh|crore)\w*", ql):
            return {"text": f"**{n.title}** budget: {n.budget}. Duration: {n.duration}." + _src(n), "intent": "budget", "sources": [n.id]}
        if re.search(r"\b(duration|how long|years|months)\w*", ql):
            return {"text": f"**{n.title}** duration: {n.duration}." + _src(n), "intent": "duration", "sources": [n.id]}
        if re.search(r"\b(document|attach|upload|certificate|letter|cv|biodata)\w*", ql):
            a = n.attachments or ["not captured in our record"]
            return {"text": f"Documents for **{n.title}**:\n\n" + "\n".join(f"- {x}" for x in a) + _src(n), "intent": "documents", "sources": [n.id]}
        if re.search(r"\b(section|format|limit|word|character|structure|proposal)\w*", ql):
            return {"text": f"Proposal format for **{n.title}**:\n\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(n.proposal_format, 1)) + _src(n), "intent": "format", "sources": [n.id]}
        if re.search(r"\b(theme|topic|about|focus|scope|what is)\w*", ql):
            return {"text": f"**{n.title}** ({n.agency}) focuses on: {n.themes}." + _src(n), "intent": "themes", "sources": [n.id]}
        return {"text": f"Here is a summary of **{n.title}** ({n.agency}):\n\n- Deadline: {_days(n, today)}\n- Budget: {n.budget}\n- Duration: {n.duration}\n- Focus: {n.themes[:200]}\n\nAsk about eligibility, documents or sections for more." + _src(n), "intent": "summary", "sources": [n.id]}
    # fallback: closest record, honest
    r = idx.search(q, today=today, include_expired=True, top_k=1)
    if r and r[0]["score"] > 0.05:
        n = r[0]["notice"]
        return {"text": f"I could not find a direct answer in my records. The closest call is **{n.title}** (match {r[0]['score']:.2f}); you can ask me about its deadline, budget, eligibility or documents." + _src(n), "intent": "fallback", "sources": [n.id]}
    return {"text": "That is not in my records, so I will not guess. I only know the 8 funding calls loaded in this prototype.", "intent": "unknown", "sources": []}
