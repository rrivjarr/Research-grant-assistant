"""Drafting + Review loop. The reviewer checks every checklist item; failures are fed back to the reviser
until compliance reaches 100% or max rounds. Without an LLM the text is a scaffold built from the
researcher's own idea, with [PI TO WRITE] markers instead of invented content."""
import re
from compiler import compile_checklist
import llm

def _count(text, unit):
    if unit == "chars": return len(text)
    if unit == "words": return len(text.split())
    if unit == "items": return len([x for x in re.split(r"[;,]", text) if x.strip()])
    return 0

def _first_draft_v1(item, profile, notice):
    """Deliberately generic first pass: knows common section types, ignores limits."""
    n = item.name.lower()
    idea = profile.idea
    if item.kind == "attachment":
        return None   # attachments are never fabricated
    if "title" in n:
        return profile.title or idea[:80]
    if "keyword" in n:
        words = [w for w in re.findall(r"[A-Za-z]{5,}", idea.lower())]
        seen = []
        for w in words:
            if w not in seen: seen.append(w)
        return "; ".join(seen[:10])
    if "summary" in n or "objective" in n or "outcome" in n or "background" in n or "rationale" in n or "problem" in n:
        base = f"{idea} " + ("This work addresses a gap in current practice and is aligned with the call's priorities. " * 6)
        return base.strip()
    return None

STOP = set("""propose proposed proposal tool tools uses using used that this with from have will which their evaluated evaluate three
about based approach system study work project research into more such also these those whose where when than then them they
through while within without across among other over under between during after before""".split())

def _fit(text, item):
    if not item.limit: return text
    if item.unit == "chars" and len(text) > item.limit:
        return text[:item.limit].rsplit(" ", 1)[0]
    if item.unit == "words":
        return " ".join(text.split()[:item.limit])
    return text

def _keywords(profile, limit=6):
    seq = re.findall(r"[a-z]{5,}", (profile.title + " " + profile.idea).lower())
    out = []
    for w in seq:
        if w in STOP or w in out: continue
        out.append(w)
    return "; ".join(out[:limit])

def _first_draft_v2(item, profile, notice):
    """Optimized pass: section-specific frames, limit-aware, no repeated text, call themes used, gaps marked."""
    n = item.name.lower(); idea = profile.idea.strip()
    themes = notice.themes.split(";")[0][:160]
    first = re.split(r"(?<=[.!?])\s", idea)[0] if idea else ""
    if item.kind == "attachment": return None
    if "title" in n: return _fit(profile.title or " ".join(idea.split()[:12]), item)
    if "keyword" in n: return _keywords(profile, item.limit or 6)
    if "summary" in n or "background" in n or "rationale" in n or "problem" in n or "significance" in n:
        return _fit(f"{idea} This proposal responds to the call '{notice.title}', which focuses on: {themes}.", item)
    if "objective" in n:
        return _fit(f"Objective 1: to develop and evaluate the approach described: {first[:150]} Objective 2: [PI TO CONFIRM: second measurable objective].", item)
    if "outcome" in n or "output" in n:
        return _fit(f"Expected outputs: [PI TO CONFIRM: measurable deliverables and numbers]. Fit with the call: {themes}.", item)
    return None

def _first_draft(item, profile, notice, version=2):
    return (_first_draft_v2 if version == 2 else _first_draft_v1)(item, profile, notice)

def _revise(item, text, issue):
    if issue.startswith("missing"):
        return f"[PI TO WRITE: {item.name}]"
    if issue.startswith("over"):
        if item.unit == "chars":
            return text[:item.limit].rsplit(" ", 1)[0]
        if item.unit == "words":
            return " ".join(text.split()[:item.limit])
        if item.unit == "items":
            parts = [x.strip() for x in re.split(r"[;,]", text) if x.strip()]
            return "; ".join(parts[:item.limit])
    return text

def review(items, draft):
    findings = []
    for it in items:
        if it.kind == "attachment":
            continue
        t = draft.get(it.name)
        if not t:
            findings.append((it, "missing section"))
        elif it.limit and _count(t, it.unit) > it.limit:
            findings.append((it, f"over limit: {_count(t, it.unit)} {it.unit} > {it.limit}"))
    return findings

def run(notice, profile, max_rounds=4, version=2):
    items = compile_checklist(notice)
    sections = [i for i in items if i.kind == "section"]
    draft = {}
    for it in sections:
        t = llm.draft_section(it.name, f"(max {it.limit} {it.unit})" if it.limit else "", profile.idea, notice.title) \
            or _first_draft(it, profile, notice, version)
        if t: draft[it.name] = t
    log = []
    for rnd in range(1, max_rounds + 1):
        findings = review(items, draft)
        score = round(100 * (len(sections) - len(findings)) / max(len(sections), 1))
        log.append({"round": rnd, "compliance": score,
                    "issues": [f"{it.name}: {msg}" for it, msg in findings]})
        if not findings:
            break
        for it, msg in findings:
            draft[it.name] = _revise(it, draft.get(it.name, ""), msg)
    placeholders = [k for k, v in draft.items() if v.startswith("[PI TO WRITE")]
    attach_todo = [i.name for i in items if i.kind == "attachment"]
    return {"version": version, "draft": draft, "log": log, "placeholders": placeholders,
            "attachments_to_collect": attach_todo, "items": items}

def to_markdown(notice, profile, result):
    md = [f"# Draft proposal scaffold: {notice.title}", "",
          f"*Source: {notice.source}*  ", "*Scaffold for the PI to complete. Text marked [PI TO WRITE] is intentionally empty.*", ""]
    for it in result["items"]:
        if it.kind == "section":
            lim = f" (max {it.limit} {it.unit})" if it.limit else ""
            md += [f"## {it.name}{lim}", result["draft"].get(it.name, "[PI TO WRITE]"), ""]
    md += ["## Attachments to collect"] + [f"- [ ] {a}" for a in result["attachments_to_collect"]]
    md += ["", "## Review log"] + [f"- Round {r['round']}: compliance {r['compliance']}%"
                                   + (f" ({len(r['issues'])} issues)" if r['issues'] else "") for r in result["log"]]
    return "\n".join(md)

def to_docx(notice, profile, result, path):
    from docx import Document
    d = Document()
    d.add_heading(f"Draft proposal scaffold: {notice.title}", 1)
    d.add_paragraph(f"Source: {notice.source}")
    d.add_paragraph("Scaffold for the PI to complete. Text marked [PI TO WRITE] is intentionally empty.")
    for it in result["items"]:
        if it.kind == "section":
            lim = f" (max {it.limit} {it.unit})" if it.limit else ""
            d.add_heading(it.name + lim, 2)
            d.add_paragraph(result["draft"].get(it.name, "[PI TO WRITE]"))
    d.add_heading("Attachments to collect", 2)
    for a in result["attachments_to_collect"]:
        d.add_paragraph(a, style="List Bullet")
    d.save(path)


def quality_metrics(result):
    """Content metrics for comparing drafter versions."""
    draft = result["draft"]
    real = {k: v for k, v in draft.items() if not v.startswith("[PI TO WRITE")}
    toks = {k: set(re.findall(r"[a-z]{4,}", v.lower())) for k, v in real.items() if len(v) > 60}
    pairs = [(a, b) for i, a in enumerate(toks) for b in list(toks)[i + 1:]]
    dup = sum(len(toks[a] & toks[b]) / max(len(toks[a] | toks[b]), 1) for a, b in pairs) / len(pairs) if pairs else 0.0
    kw = draft.get([k for k in draft if "eyword" in k][0], "") if any("eyword" in k for k in draft) else ""
    noise = sum(1 for w in kw.split(";") if w.strip() in STOP)
    return {"first_pass": result["log"][0]["compliance"], "final": result["log"][-1]["compliance"],
            "rounds": len(result["log"]), "real_sections": len(real), "total_sections": len(draft),
            "duplication": round(dup, 2), "keyword_noise": noise}
