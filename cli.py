"""CLI: python cli.py discover|check|draft ..."""
import argparse, json, datetime as dt, sys
from retrieval import Index
from eligibility import Profile, check, explain
from compiler import compile_checklist, show
import drafter

def load_profile(path):
    d = json.load(open(path))
    d["degrees"] = tuple(d.get("degrees", []))
    return Profile(**d)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["discover", "check", "draft", "checklist"])
    ap.add_argument("--query", default="")
    ap.add_argument("--profile")
    ap.add_argument("--notice")
    ap.add_argument("--today", default=None, help="as-of date YYYY-MM-DD")
    ap.add_argument("--include-expired", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    idx = Index()
    if a.cmd == "discover":
        q = a.query
        p = load_profile(a.profile) if a.profile else None
        if p and not q: q = p.idea
        print(f"As of {today}. Query: {q!r}")
        for r in idx.search(q, today=today, include_expired=a.include_expired):
            n = r["notice"]
            print(f"  {r['final']:.3f}  {n.id:16} {r['status']:26} {n.title}")
            if p:
                res = check(n, p, today)
                print(f"           -> {res['verdict']}")
    elif a.cmd == "check":
        p = load_profile(a.profile)
        targets = [idx.by_id[a.notice]] if a.notice else idx.notices
        for n in targets:
            print(explain(check(n, p, today))); print()
    elif a.cmd == "checklist":
        print(show(compile_checklist(idx.by_id[a.notice])))
    elif a.cmd == "draft":
        p = load_profile(a.profile); n = idx.by_id[a.notice]
        res = drafter.run(n, p)
        for r in res["log"]:
            print(f"Round {r['round']}: compliance {r['compliance']}%", *r["issues"], sep="\n   - " if r["issues"] else "")
        filled = len(res["draft"]) - len(res["placeholders"]); total = len(res["draft"])
        print(f"Structural compliance reached; content actually drafted: {filled}/{total} sections, {len(res['placeholders'])} left as [PI TO WRITE]")
        if a.out:
            drafter.to_docx(n, p, res, a.out + ".docx")
            open(a.out + ".md", "w").write(drafter.to_markdown(n, p, res))
            print(f"Wrote {a.out}.docx and {a.out}.md")
        else:
            print(drafter.to_markdown(n, p, res))

if __name__ == "__main__":
    main()
