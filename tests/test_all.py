import sys, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from ingest import load_notices
from retrieval import Index
from eligibility import Profile, check
from compiler import compile_checklist
import drafter

TODAY = dt.date(2026, 11, 25)
def prof(name):
    d = json.load(open(Path(__file__).parent.parent / "data/profiles" / f"{name}.json"))
    d["degrees"] = tuple(d["degrees"]); return Profile(**d)

def test_parse_all_notices():
    ns = load_notices()
    assert len(ns) == 8 and all(n.source.startswith("https://") for n in ns)

def test_expired_filtered_by_default():
    ids = [r["notice"].id for r in Index().search("microbiome human health therapeutics", today=TODAY)]
    assert "DBT-MICROBIOME" not in ids
    ids2 = [r["notice"].id for r in Index().search("microbiome human health therapeutics", today=TODAY, include_expired=True)]
    assert ids2[0] == "DBT-MICROBIOME"

def test_age_near_miss_ravi_srg():
    idx = Index(); r = check(idx.by_id["SERB-ECRA"], prof("ravi"), TODAY)
    assert r["verdict"].startswith("NEAR MISS") and "37" in r["blockers"][0].why

def test_age_relaxation_for_women():
    p = prof("ravi"); p.gender = "F"
    r = check(Index().by_id["SERB-ECRA"], p, TODAY)
    assert not r["blockers"]

def test_ne_state_rule():
    assert check(Index().by_id["DHR-NER-HRD"], prof("asha"), TODAY)["verdict"].startswith("NEAR MISS")
    assert check(Index().by_id["DHR-NER-HRD"], prof("meena"), TODAY)["verdict"].startswith("ELIGIBLE")

def test_checklist_limits_parsed():
    items = compile_checklist(Index().by_id["SERB-SRG"])
    t = [i for i in items if i.name.startswith("Project title")][0]
    assert (t.limit, t.unit) == (500, "chars")

def test_review_loop_reaches_full_compliance():
    n = Index().by_id["SERB-SRG"]; res = drafter.run(n, prof("asha"))
    assert res["log"][0]["compliance"] < 100 and res["log"][-1]["compliance"] == 100
    for it in res["items"]:
        if it.kind == "section" and it.limit:
            assert drafter._count(res["draft"][it.name], it.unit) <= it.limit

def test_attachments_never_fabricated():
    res = drafter.run(Index().by_id["SERB-SRG"], prof("asha"))
    assert "Biodata" in res["attachments_to_collect"] and "Biodata" not in res["draft"]
