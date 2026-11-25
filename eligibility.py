"""Clause-level eligibility check with citations and 'Explain Why Not' near-miss logic.
Each notice clause is matched by a rule; unmatched clauses are reported as 'manual check'."""
import re, datetime as dt
from dataclasses import dataclass

NE_STATES = {"arunachal pradesh","assam","manipur","meghalaya","mizoram","nagaland","sikkim","tripura"}
RELAX_CATS = {"SC","ST","OBC","PWD"}

@dataclass
class Profile:
    name: str = ""
    age: int = 0
    gender: str = ""            # "F"/"M"/"O"
    citizenship: str = "Indian"
    degrees: tuple = ()         # e.g. ("PhD Engineering",)
    position: str = ""          # regular | contractual | postdoc | unemployed | student
    months_since_joining: int = 0
    category: str = "General"   # General/SC/ST/OBC/PwD
    state: str = ""
    institution: str = "university"   # university | medical college | ngo | industry | national lab
    prior_serb_grant: bool = False
    idea: str = ""
    title: str = ""

@dataclass
class ClauseResult:
    clause: str
    status: str                 # PASS / FAIL / MANUAL
    why: str

def _has_degree(p, words):
    return any(any(w in d.lower() for w in words) for d in p.degrees)

def check_clause(clause, p: Profile):
    c = clause.lower()
    # age limit (with relaxation)
    m = re.search(r"age (?:limit )?(?:is|must be up to) (\d+)", c) or re.search(r"upper age limit is (\d+)", c)
    if m:
        lim = int(m.group(1))
        relax = ("relaxation" in c)
        cat_ok = p.category.upper() in RELAX_CATS or p.gender == "F"
        if p.age <= lim:
            return "PASS", f"age {p.age} <= {lim}"
        if relax and cat_ok and p.age <= lim + 3:
            return "PASS", f"age {p.age} exceeds {lim} but the 3-year relaxation applies to this profile"
        extra = " (a 3-year relaxation exists for SC/ST/OBC/PwD/women, but this profile does not qualify)" if relax else ""
        return "FAIL", f"age {p.age} exceeds the limit of {lim}{extra}"
    if "indian citizen" in c:
        return ("PASS", "Indian citizen") if p.citizenship.lower() == "indian" else ("FAIL", f"citizenship is {p.citizenship}")
    if "indian national residing in india" in c:
        return ("PASS", "Indian national") if p.citizenship.lower() == "indian" else ("FAIL", f"citizenship is {p.citizenship}")
    if "must be a woman" in c:
        return ("PASS", "woman applicant") if p.gender == "F" else ("FAIL", "call is only for women")
    if "unemployed" in c:
        return ("PASS", "unemployed on closing date") if p.position == "unemployed" else ("FAIL", f"current status is '{p.position}', call needs an unemployed applicant")
    if "regular" in c and "holding" in c and "mbbs" in c and "must" in c:
        if p.position != "regular":
            return "FAIL", f"position is '{p.position}', regular faculty is required"
        if not _has_degree(p, ["mbbs", "md", "ms", "dm"]):
            return "FAIL", f"degrees {list(p.degrees) or 'none stated'} do not include MBBS, MD, MS or DM"
        return "PASS", "regular faculty with a qualifying medical degree"
    if "regular" in c and ("position" in c or "post" in c or "faculty" in c) and "must" in c:
        if p.position == "regular":
            return "PASS", "holds a regular position"
        return "FAIL", f"position is '{p.position}', a regular/finalised post is required"
    if "within two years of joining" in c:
        if p.months_since_joining <= 24:
            return "PASS", f"joined {p.months_since_joining} months ago (<= 24)"
        return "FAIL", f"joined {p.months_since_joining} months ago, limit is 24"
    if "already received a serb grant" in c:
        return ("FAIL", "has a prior SERB grant") if p.prior_serb_grant else ("PASS", "no prior SERB grant")
    if "north eastern state" in c:
        return ("PASS", f"state {p.state} is in the NE region") if p.state.lower() in NE_STATES else ("FAIL", f"state '{p.state or 'unknown'}' is not a North Eastern state")
    if "phd" in c or "mbbs" in c or "mtech" in c:
        words = []
        if "phd" in c: words += ["phd"]
        if "mbbs" in c: words += ["mbbs", "md", "ms", "dm"]
        if "md" in c or " ms " in c: words += ["md", "ms"]
        if "mtech" in c: words += ["mtech", "m.tech", "mpharm", "m.pharm"]
        if _has_degree(p, words):
            return "PASS", "holds a qualifying degree"
        return "FAIL", f"degrees {list(p.degrees) or 'none stated'} do not match the required qualification"
    if "startup" in c or "recognised r&d lab" in c:
        ok = p.institution in {"university", "medical college", "ngo", "industry", "national lab"}
        return ("PASS", f"institution type '{p.institution}' is covered") if ok else ("FAIL", "institution type not covered")
    if "medical college" in c or "medical institution" in c:
        return ("PASS", "medical institution") if p.institution == "medical college" else ("FAIL", f"institution type is '{p.institution}'")
    if "enrolled in higher studies" in c:
        return ("FAIL", "currently a student/fellow") if p.position == "student" else ("PASS", "not enrolled in studies")
    return "MANUAL", "no automatic rule for this clause; read it yourself"

def check(notice, p: Profile, today=None):
    today = today or dt.date.today()
    results = []
    status = notice.status(today)
    if status == "EXPIRED":
        results.append(ClauseResult(f"Deadline {notice.deadline}", "FAIL", f"call closed on {notice.deadline} (as of {today})"))
    for clause in notice.eligibility:
        st, why = check_clause(clause, p)
        results.append(ClauseResult(clause, st, why))
    expired = status == "EXPIRED"
    fails = [r for r in results if r.status == "FAIL" and not r.clause.startswith("Deadline")]
    manual = [r for r in results if r.status == "MANUAL"]
    if not fails:
        verdict = "ELIGIBLE (verify manual clauses)" if manual else "ELIGIBLE"
    elif len(fails) == 1:
        verdict = "NEAR MISS: one blocker"
    else:
        verdict = f"NOT ELIGIBLE: {len(fails)} blockers"
    if expired:
        verdict = f"CLOSED on {notice.deadline} (profile otherwise: {verdict})"
    return {"notice": notice, "verdict": verdict, "results": results, "blockers": fails}

def explain(res):
    n = res["notice"]
    lines = [f"{n.id}: {res['verdict']}"]
    for r in res["results"]:
        tag = {"PASS": "[ok]  ", "FAIL": "[FAIL]", "MANUAL": "[check]"}[r.status]
        lines.append(f"  {tag} {r.clause}\n         -> {r.why}")
    return "\n".join(lines)
