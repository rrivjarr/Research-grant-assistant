"""Evaluation harness. Test cases are written by hand from the call wording (expected labels are NOT taken from program output).
Run: python eval.py   -> prints a report and writes outputs/eval_results.json"""
import json, datetime as dt, copy, sys
from pathlib import Path
from retrieval import Index
from eligibility import Profile, check
import drafter, chatbot

BASE = dict(name="t", age=34, gender="F", citizenship="Indian", degrees=("PhD Engineering",), position="regular",
            months_since_joining=10, category="General", state="Karnataka", institution="university",
            prior_serb_grant=False, idea="We propose a retrieval augmented decision support tool for rural clinics using low cost sensors.",
            title="Retrieval-augmented triage of rural clinic referrals")
D = dt.date
def P(**kw): d = dict(BASE); d.update(kw); return Profile(**d)

# (id, call, profile, as_of, expected class: ELIGIBLE | NEAR | NOT | CLOSED)
ELIG = [
 ("E01", "SERB-SRG", P(), D(2026,11,25), "ELIGIBLE"),
 ("E02", "SERB-SRG", P(age=46), D(2026,11,25), "NEAR"),
 ("E03", "SERB-SRG", P(age=44), D(2026,11,25), "ELIGIBLE"),
 ("E04", "SERB-SRG", P(age=44, gender="M"), D(2026,11,25), "NEAR"),
 ("E05", "SERB-SRG", P(position="contractual"), D(2026,11,25), "NEAR"),
 ("E06", "SERB-SRG", P(months_since_joining=30), D(2026,11,25), "NEAR"),
 ("E07", "SERB-SRG", P(prior_serb_grant=True), D(2026,11,25), "NEAR"),
 ("E08", "SERB-SRG", P(position="contractual", months_since_joining=30), D(2026,11,25), "NOT"),
 ("E09", "SERB-SRG", P(citizenship="Nepali"), D(2026,11,25), "NEAR"),
 ("E10", "SERB-ECRA", P(age=39, gender="M"), D(2026,11,25), "NEAR"),
 ("E11", "SERB-ECRA", P(age=39, gender="F"), D(2026,11,25), "ELIGIBLE"),
 ("E12", "SERB-ECRA", P(age=41, gender="F"), D(2026,11,25), "NEAR"),
 ("E13", "SERB-ECRA", P(age=36, gender="M", category="SC", position="postdoc"), D(2026,11,25), "NEAR"),
 ("E14", "SERB-CRG", P(), D(2026,11,25), "ELIGIBLE"),
 ("E15", "SERB-CRG", P(position="contractual"), D(2026,11,25), "NEAR"),
 ("E16", "DBT-BIOCARE", P(age=41, position="unemployed", degrees=("PhD Biotechnology",)), D(2026,9,1), "ELIGIBLE"),
 ("E17", "DBT-BIOCARE", P(age=41, position="unemployed", degrees=("PhD Biotechnology",)), D(2026,11,25), "CLOSED"),
 ("E18", "DBT-BIOCARE", P(age=41, gender="M", position="unemployed", degrees=("PhD Biotechnology",)), D(2026,9,1), "NEAR"),
 ("E19", "DBT-BIOCARE", P(age=41, position="regular", degrees=("PhD Biotechnology",)), D(2026,9,1), "NEAR"),
 ("E20", "DBT-BIOCARE", P(age=58, position="unemployed", degrees=("PhD Biotechnology",)), D(2026,9,1), "NEAR"),
 ("E21", "DHR-NER-HRD", P(state="Assam"), D(2026,11,25), "ELIGIBLE"),
 ("E22", "DHR-NER-HRD", P(state="Karnataka"), D(2026,11,25), "NEAR"),
 ("E23", "ICMR-FIW-2026", P(), D(2026,11,25), "ELIGIBLE"),
 ("E24", "ICMR-NMC-MEDEDU", P(institution="medical college", degrees=("MD Medicine",)), D(2026,8,1), "ELIGIBLE"),
 ("E25", "ICMR-NMC-MEDEDU", P(), D(2026,8,1), "NOT"),
 ("E26", "ICMR-NMC-MEDEDU", P(institution="medical college", degrees=("MD Medicine",)), D(2026,11,25), "CLOSED"),
 ("E27", "DBT-MICROBIOME", P(), D(2026,10,1), "ELIGIBLE"),
 ("E28", "DBT-MICROBIOME", P(), D(2026,11,25), "CLOSED"),
]
def cls(v):
    return "ELIGIBLE" if v.startswith("ELIGIBLE") else "NEAR" if v.startswith("NEAR") else "CLOSED" if v.startswith("CLOSED") else "NOT"

RET = [ # (query, expected call id)
 ("early career researcher award young scientists age limit", "SERB-ECRA"),
 ("start-up grant for faculty who joined recently", "SERB-SRG"),
 ("women researchers unemployed biotechnology programme", "DBT-BIOCARE"),
 ("microbiome therapeutics human health", "DBT-MICROBIOME"),
 ("medical education competency based teaching", "ICMR-NMC-MEDEDU"),
 ("first of its kind vaccine drug diagnostic prototype", "ICMR-FIW-2026"),
 ("North Eastern region health research fellowship", "DHR-NER-HRD"),
 ("core research support frontier science and engineering", "SERB-CRG"),
 ("high risk high reward biomedical innovation startup MSME", "ICMR-FIW-2026"),
 ("plagiarism undertaking originality", "SERB-CRG"),
 ("women scientist fellowship NRI PIO", "DHR-NER-HRD"),
 ("Rs 50 lakh three years excluding overheads", "SERB-ECRA"),
]
CHAT = [ # (question, must contain substring (lowercase), expected intent)
 ("What is the deadline for the ICMR First in the World call?", "30 nov 2026", "deadline"),
 ("How much funding does the First in the World challenge give?", "8 crore", "budget"),
 ("What documents do I need for the SERB Start-up Research Grant?", "biodata", "documents"),
 ("Which calls are open right now?", "first in the world", "open"),
 ("Am I eligible for the SERB Early Career Research Award?", "eligible", "eligibility"),
 ("Compare SRG and ECRA", "serb-srg", "compare"),
 ("How long is the BioCARe programme?", "3 years", "duration"),
 ("What is the capital of France?", "not in my records", "unknown"),
]

def run(today=D(2026,11,25)):
    idx = Index(); out = {}
    # 1 eligibility
    rows = []
    for cid, call, prof, asof, exp in ELIG:
        got = cls(check(idx.by_id[call], prof, asof)["verdict"])
        rows.append({"id": cid, "call": call, "expected": exp, "got": got, "ok": got == exp})
    out["eligibility"] = {"n": len(rows), "correct": sum(r["ok"] for r in rows), "rows": rows}
    # 2 retrieval
    rr = []
    for q, exp in RET:
        res = idx.search(q, today=today, include_expired=True, top_k=8)
        ids = [r["notice"].id for r in res]
        rank = ids.index(exp) + 1 if exp in ids else None
        rr.append({"query": q, "expected": exp, "rank": rank})
    out["retrieval"] = {"n": len(rr), "hit1": sum(1 for r in rr if r["rank"] == 1), "hit3": sum(1 for r in rr if r["rank"] and r["rank"] <= 3),
                        "mrr": round(sum(1 / r["rank"] for r in rr if r["rank"]) / len(rr), 3), "rows": rr}
    # 3 drafting: v1 vs v2 across all calls
    comp = {1: [], 2: []}
    for v in (1, 2):
        for n in idx.notices:
            res = drafter.run(n, P(), version=v); m = drafter.quality_metrics(res)
            viol = sum(1 for it in res["items"] if it.kind == "section" and it.limit and it.name in res["draft"] and drafter._count(res["draft"][it.name], it.unit) > it.limit)
            m["limit_violations_final"] = viol; m["call"] = n.id; comp[v].append(m)
    avg = lambda v, k: round(sum(m[k] for m in comp[v]) / len(comp[v]), 2)
    out["drafting"] = {"v1": {k: avg(1, k) for k in ("first_pass", "final", "rounds", "duplication", "keyword_noise", "limit_violations_final")},
                       "v2": {k: avg(2, k) for k in ("first_pass", "final", "rounds", "duplication", "keyword_noise", "limit_violations_final")}, "per_call": comp}
    # 4 chatbot
    cr = []
    for q, sub, intent in CHAT:
        a = chatbot.answer(q, idx, P(age=34), today)
        cr.append({"q": q, "intent_ok": a["intent"] == intent, "content_ok": sub in a["text"].lower(), "cited": ("Source" in a["text"] or "Sources" in a["text"] or a["intent"] in ("unknown", "open", "help"))})
    out["chatbot"] = {"n": len(cr), "intent_ok": sum(r["intent_ok"] for r in cr), "content_ok": sum(r["content_ok"] for r in cr), "cited": sum(r["cited"] for r in cr), "rows": cr}
    return out

if __name__ == "__main__":
    r = run()
    e, t, dr, c = r["eligibility"], r["retrieval"], r["drafting"], r["chatbot"]
    print(f"Eligibility: {e['correct']}/{e['n']} correct ({100*e['correct']/e['n']:.0f}%)")
    for x in e["rows"]:
        if not x["ok"]: print("   MISMATCH", x)
    print(f"Retrieval: hit@1 {t['hit1']}/{t['n']}, hit@3 {t['hit3']}/{t['n']}, MRR {t['mrr']}")
    for x in t["rows"]:
        if x["rank"] != 1: print("   not top-1:", x)
    print("Drafting v1:", dr["v1"]); print("Drafting v2:", dr["v2"])
    print(f"Chatbot: intent {c['intent_ok']}/{c['n']}, content {c['content_ok']}/{c['n']}, cited {c['cited']}/{c['n']}")
    for x in c["rows"]:
        if not (x["intent_ok"] and x["content_ok"]): print("   FAIL", x)
    Path("outputs").mkdir(exist_ok=True); json.dump(r, open("outputs/eval_results.json", "w"), indent=1, default=str)
