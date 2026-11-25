"""Research Grant Assistant (final): streamlit run app.py"""
import dataclasses, datetime as dt, json, tempfile
from pathlib import Path
import pandas as pd
import streamlit as st
from retrieval import Index
from eligibility import Profile, check
from compiler import compile_checklist
import drafter, chatbot
import eval as evaluation

st.set_page_config(page_title="Research Grant Assistant", page_icon="🎓", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
#MainMenu, footer {visibility:hidden;}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button {visibility:visible !important; opacity:1 !important; background:#ffffff !important; border:2px solid #111827 !important; border-radius:8px !important; color:#000000 !important;}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapseButton"] button * {color:#000000 !important; fill:#000000 !important;}
[data-testid="stExpandSidebarButton"] {box-shadow:0 2px 6px rgba(0,0,0,.25);}
.block-container {padding-top:1.1rem; max-width:1300px;}
.hero {background:linear-gradient(120deg,#1e3a8a 0%,#2563eb 60%,#0ea5e9 100%); color:#fff; padding:24px 30px; border-radius:16px; margin-bottom:12px;}
.hero h1 {margin:0; font-size:2rem; color:#fff;} .hero p {margin:6px 0 0 0; opacity:.92;}
.chips span {display:inline-block; background:rgba(255,255,255,.18); padding:4px 12px; border-radius:999px; margin:12px 8px 0 0; font-size:.85rem;}
.card {border:1px solid #e5e7eb; border-radius:14px; padding:15px 18px; margin-bottom:6px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05);}
.card h4 {margin:0 0 4px 0; font-size:1.05rem; color:#111827;} .meta {color:#6b7280; font-size:.85rem;}
.pill {display:inline-block; padding:3px 11px; border-radius:999px; font-size:.78rem; font-weight:600; margin-right:6px;}
.p-green {background:#dcfce7; color:#166534;} .p-amber {background:#fef3c7; color:#92400e;} .p-red {background:#fee2e2; color:#991b1b;}
.p-grey {background:#e5e7eb; color:#374151;} .p-blue {background:#dbeafe; color:#1e40af;}
.why {margin-top:8px; font-size:.9rem; color:#374151;}
.step {background:#f1f5f9; border-radius:12px; padding:14px 16px; height:100%;} .step b {color:#1e3a8a;}
.rai {border-left:4px solid #2563eb; background:#f8fafc; padding:10px 14px; border-radius:8px; margin-bottom:10px;}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_index(): return Index()
@st.cache_data
def get_eval(): return evaluation.run()

idx = get_index()
PROFILES = {p.stem: json.load(open(p)) for p in sorted(Path("data/profiles").glob("*.json"))}
PG = ["🔎 Find calls", "✅ Eligibility", "📝 Proposal", "⚖️ Compare", "💬 Assistant", "📊 Evaluation", "🛡️ Responsible AI", "ℹ️ About"]
SAMPLE = {"asha": "Asha: early-career woman, regular post", "ravi": "Ravi: slightly over the age limit", "meena": "Meena: unemployed woman, Assam"}

def kind(v):
    if v.startswith("ELIGIBLE"): return "green", "Eligible"
    if v.startswith("NEAR"): return "amber", "Near miss"
    if v.startswith("CLOSED"): return "grey", "Closed"
    return "red", "Not eligible"
def pill(v):
    c, t = kind(v); return f'<span class="pill p-{c}">{t}</span>'
def go(page, call_id=None):
    st.session_state["page"] = page
    if call_id: st.session_state["sel"] = call_id

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### 👤 About the researcher")
    opts = ["(enter my own)"] + list(PROFILES)
    preset = st.selectbox("Start from a sample", opts, index=opts.index("asha") if "asha" in opts else 0, format_func=lambda k: SAMPLE.get(k, k))
    d = PROFILES.get(preset, {})
    idea = st.text_area("Your research idea", d.get("idea", ""), height=110, placeholder="Describe the project in 2-3 sentences")
    title = st.text_input("Working title", d.get("title", ""))
    with st.expander("Personal details", expanded=True):
        age = st.number_input("Age", 18, 80, int(d.get("age", 35)))
        gender = st.selectbox("Gender", ["F", "M", "O"], index=["F", "M", "O"].index(d.get("gender", "F")))
        cats = ["General", "SC", "ST", "OBC", "PwD"]
        category = st.selectbox("Category", cats, index=cats.index(d.get("category", "General")))
        state = st.text_input("State", d.get("state", ""))
    with st.expander("Qualification and job"):
        degrees = st.text_input("Degrees (comma separated)", ", ".join(d.get("degrees", ["PhD Engineering"])))
        positions = ["regular", "contractual", "postdoc", "unemployed", "student"]
        position = st.selectbox("Current position", positions, index=positions.index(d.get("position", "regular")))
        months = st.number_input("Months since joining institution", 0, 600, int(d.get("months_since_joining", 12)))
        insts = ["university", "medical college", "ngo", "industry", "national lab"]
        institution = st.selectbox("Institution type", insts, index=insts.index(d.get("institution", "university")))
        prior = st.checkbox("Already holds a SERB grant", d.get("prior_serb_grant", False))
    with st.expander("Date and filters"):
        today = st.date_input("Today's date (for deadlines)", dt.date(2026, 11, 25))
        show_closed = st.checkbox("Include closed calls", True)
    st.caption("🔒 Your details stay in this session only. Nothing is stored or sent anywhere.")

profile = Profile(name=preset, age=int(age), gender=gender, category=category,
                  degrees=tuple(x.strip() for x in degrees.split(",") if x.strip()), position=position,
                  months_since_joining=int(months), state=state, institution=institution, prior_serb_grant=prior, idea=idea, title=title)

# ----------------------------------------------------------------- chat state
if "chat" not in st.session_state: st.session_state["chat"] = []
def chat_reply(q):
    st.session_state["chat"].append(("user", q))
    st.session_state["chat"].append(("assistant", chatbot.answer(q, idx, profile, today)["text"]))

open_calls = sum(1 for n in idx.notices if n.status(today) == "OPEN")
st.markdown(f"""<div class="hero"><h1>🎓 Research Grant Assistant</h1>
<p>Find the right funding call, see exactly why you do or don't qualify, ask questions, and build a proposal that follows the call's rules.</p>
<div class="chips"><span>📚 {len(idx.notices)} real Indian calls</span><span>🟢 {open_calls} open on {today:%d %b %Y}</span>
<span>SERB · DBT · ICMR · DHR</span><span>Hackathon PS 52 · Category K</span></div></div>""", unsafe_allow_html=True)

if "page" not in st.session_state: st.session_state["page"] = PG[0]
nav, chatcol = st.columns([6, 1.3])
page = nav.radio("Pages", PG, horizontal=True, key="page", label_visibility="collapsed")
with chatcol.popover("💬 Ask the assistant", width="stretch"):
    st.caption("Ask about deadlines, budgets, eligibility, documents, sections.")
    with st.form("quickchat", clear_on_submit=True):
        qq = st.text_input("Your question", placeholder="e.g. Am I eligible for SRG?", label_visibility="collapsed")
        sent = st.form_submit_button("Ask", width="stretch")
    if sent and qq.strip(): chat_reply(qq.strip())
    for role, text in st.session_state["chat"][-4:]:
        with st.chat_message(role): st.markdown(text)
ids = [n.id for n in idx.notices]; titles = {n.id: n.title for n in idx.notices}
today_ = today

def ics_for(notices):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Research Grant Assistant//EN"]
    for n in notices:
        dd = n.deadline_date()
        if dd and dd >= today_:
            lines += ["BEGIN:VEVENT", f"UID:{n.id}@grant-assistant", f"DTSTAMP:{today_:%Y%m%d}T000000Z", f"DTSTART;VALUE=DATE:{dd:%Y%m%d}",
                      f"SUMMARY:Deadline: {n.title}", f"DESCRIPTION:{n.source}", "END:VEVENT"]
    lines.append("END:VCALENDAR"); return "\r\n".join(lines)

# ================================================================= 1 FIND
if page == PG[0]:
    c1, c2, c3 = st.columns([3, 2, 1.6])
    query = c1.text_input("What are you looking for?", "", placeholder="Leave blank to use your research idea, or type e.g. microbiome")
    agencies = sorted({n.agency.split(" ")[0] for n in idx.notices})
    ag = c2.multiselect("Funding agency", agencies)
    sort = c3.selectbox("Sort by", ["Best for me", "Deadline soonest", "Best text match"])
    q = query or idea or "research"
    rows = []
    for r in idx.search(q, today=today, include_expired=show_closed, top_k=20):
        n = r["notice"]
        if ag and n.agency.split(" ")[0] not in ag: continue
        rows.append((r, check(n, profile, today)))
    order = {"green": 0, "amber": 1, "red": 2, "grey": 3}
    if sort == "Best for me": rows.sort(key=lambda t: (order[kind(t[1]["verdict"])[0]], -t[0]["score"]))
    elif sort == "Deadline soonest": rows.sort(key=lambda t: (t[0]["notice"].deadline_date() is None, t[0]["notice"].deadline_date() or dt.date.max))
    else: rows.sort(key=lambda t: -t[0]["score"])
    counts = {"green": 0, "amber": 0, "grey": 0, "red": 0}
    for _, res in rows: counts[kind(res["verdict"])[0]] += 1
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🟢 Eligible", counts["green"]); m2.metric("🟡 Near miss", counts["amber"]); m3.metric("🔴 Not eligible", counts["red"]); m4.metric("⚪ Closed", counts["grey"])
    export = pd.DataFrame([{"Call": r["notice"].title, "Agency": r["notice"].agency, "Deadline": r["notice"].deadline_text,
                            "Verdict": res["verdict"], "Blocker": res["blockers"][0].why if res["blockers"] else "", "Source": r["notice"].source} for r, res in rows])
    d1, d2, _ = st.columns([1.4, 1.8, 4])
    d1.download_button("⬇ Shortlist (CSV)", export.to_csv(index=False), "shortlist.csv", width="stretch")
    d2.download_button("📅 Deadline reminders (.ics)", ics_for([r["notice"] for r, _ in rows]), "deadlines.ics", width="stretch")
    st.markdown("##### Your matching calls")
    if not rows: st.info("No calls match. Try a different query or tick 'Include closed calls'.")
    for r, res in rows:
        n = r["notice"]; _, label = kind(res["verdict"]); bl = res["blockers"]
        why = "You meet every rule we can check automatically." if label == "Eligible" else (
            "Blocker: " + bl[0].why + (f" (+{len(bl)-1} more)" if len(bl) > 1 else "")) if bl else f"Deadline passed on {n.deadline}."
        dd = n.deadline_date(); extra = ""
        if dd and dd >= today:
            k = (dd - today).days; extra = f'<span class="pill p-{"red" if k <= 7 else "blue"}">{"⏰ " if k <= 7 else ""}{k} days left</span>'
        left, right = st.columns([5, 1.3])
        left.markdown(f"""<div class="card"><h4>{n.title}</h4><div class="meta">{n.agency} · Deadline: {n.deadline_text if n.deadline else 'not stated'} · Budget: {n.budget[:60]}</div>
<div style="margin-top:8px">{pill(res['verdict'])}{extra}<span class="meta">match {r['score']:.2f}</span></div><div class="why">{why}</div></div>""", unsafe_allow_html=True)
        right.button("See details →", key=f"go_{n.id}", on_click=go, args=(PG[1], n.id), width="stretch")

# ================================================================= 2 ELIGIBILITY
elif page == PG[1]:
    sel = st.selectbox("Funding call", ids, format_func=lambda i: titles[i], key="sel")
    n = idx.by_id[sel]; res = check(n, profile, today); c, label = kind(res["verdict"])
    ok = sum(1 for x in res["results"] if x.status == "PASS" and not x.clause.startswith("Deadline"))
    bad = len(res["blockers"]); man = sum(1 for x in res["results"] if x.status == "MANUAL")
    st.markdown(f"### {n.title}  {pill(res['verdict'])}", unsafe_allow_html=True)
    a, b, c3, d4 = st.columns(4)
    a.metric("Rules passed", ok); b.metric("Rules failed", bad); c3.metric("To check by you", man); d4.metric("Deadline", n.deadline_text if n.deadline else "not stated")
    if label == "Near miss": st.warning(f"**You are one step away.** Only this rule fails: {res['blockers'][0].why}.")
    elif label == "Eligible": st.success("You pass every rule we can check automatically. Read the 'check yourself' items below.")
    elif label == "Closed": st.info(f"This call closed on {n.deadline}. Verdict if it were open: {res['verdict'].split('otherwise: ')[-1].rstrip(')')}.")
    else: st.error(f"{bad} rules fail for this profile.")
    st.markdown("#### Rule by rule")
    st.dataframe(pd.DataFrame([{"Result": {"PASS": "✅ Pass", "FAIL": "❌ Fail", "MANUAL": "🔍 Check yourself"}[x.status], "Rule from the call": x.clause, "What we found": x.why} for x in res["results"]]),
                 hide_index=True, width="stretch")
    if res["blockers"]:
        st.markdown("#### What you would need")
        for x in res["blockers"]: st.markdown(f"- **To pass:** {x.clause}  \n  *Today: {x.why}*")
    with st.expander("🧪 What-if: change your profile and see the verdict", expanded=False):
        w1, w2, w3, w4 = st.columns(4)
        wa = w1.number_input("Age", 18, 80, int(profile.age), key="wi_age"); wp = w2.selectbox("Position", positions, index=positions.index(profile.position), key="wi_pos")
        wc = w3.selectbox("Category", cats, index=cats.index(profile.category), key="wi_cat"); ws = w4.text_input("State", profile.state, key="wi_state")
        alt = dataclasses.replace(profile, age=int(wa), position=wp, category=wc, state=ws); r2 = check(n, alt, today)
        st.markdown(f"Now: {pill(res['verdict'])} → What-if: {pill(r2['verdict'])}", unsafe_allow_html=True)
        for x in r2["blockers"]: st.caption(f"❌ {x.clause}: {x.why}")
    with st.expander("Call facts"):
        st.markdown(f"**Agency:** {n.agency}  \n**Budget:** {n.budget}  \n**Duration:** {n.duration}  \n**Themes:** {n.themes}  \n**Source (verify here):** [{n.source}]({n.source})")
    b1, b2 = st.columns([1, 1])
    b1.button("Build a proposal for this call →", on_click=go, args=(PG[2], sel))
    b2.button("💬 Ask the assistant about this call", on_click=lambda: (go(PG[4]), chat_reply(f"Am I eligible for {n.title}?")))

# ================================================================= 3 PROPOSAL
elif page == PG[2]:
    sel = st.selectbox("Funding call", ids, format_func=lambda i: titles[i], key="sel")
    n = idx.by_id[sel]; items = compile_checklist(n)
    secs = [i for i in items if i.kind == "section"]; atts = [i for i in items if i.kind == "attachment"]
    st.markdown(f"### {n.title}")
    left, right = st.columns([2, 3])
    with left:
        st.markdown("#### What the call requires"); st.caption("Read automatically from the call document")
        st.dataframe(pd.DataFrame([{"#": i, "Section": it.name, "Limit": f"{it.limit} {it.unit}" if it.limit else "none"} for i, it in enumerate(secs, 1)]), hide_index=True, width="stretch")
        if atts:
            st.markdown("**Documents to attach**")
            for a in atts: st.markdown(f"- {a.name}")
    with right:
        st.markdown("#### Draft and review loop"); st.caption("Write a first draft, check it against every rule on the left, fix, repeat.")
        ver = st.radio("Drafting prompt version", ["v2 optimized (recommended)", "v1 initial"], horizontal=True)
        if not idea.strip(): st.warning("Add your research idea in the sidebar first.")
        if st.button("▶ Run draft and review", type="primary", disabled=not idea.strip()):
            v = 2 if ver.startswith("v2") else 1
            st.session_state["draft"] = (sel, drafter.run(n, profile, version=v), v)
        if "draft" in st.session_state and st.session_state["draft"][0] == sel:
            res = st.session_state["draft"][1]; log = res["log"]; q = drafter.quality_metrics(res)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("First draft score", f"{log[0]['compliance']}%"); k2.metric("Final score", f"{log[-1]['compliance']}%", delta=f"{log[-1]['compliance']-log[0]['compliance']}%")
            k3.metric("Sections with real text", f"{q['real_sections']}/{q['total_sections']}"); k4.metric("Repetition between sections", f"{int(q['duplication']*100)}%")
            st.bar_chart(pd.DataFrame({"Compliance %": [r["compliance"] for r in log]}, index=[f"Round {r['round']}" for r in log]), height=160)
            for r in log:
                if r["issues"]:
                    st.markdown(f"**Round {r['round']} found {len(r['issues'])} issue(s):**")
                    for iss in r["issues"]: st.markdown(f"- {iss}")
            st.info("100% means the draft follows the call's structure. Text marked [PI TO WRITE] or [PI TO CONFIRM] still needs your own content; nothing is invented.")
            st.markdown("#### Edit your draft")
            edited = {}
            for it in secs:
                txt = res["draft"].get(it.name, "[PI TO WRITE]"); used = drafter._count(txt, it.unit) if it.limit else None
                with st.expander(it.name if not it.limit else f"{it.name}  ({used}/{it.limit} {it.unit})"):
                    edited[it.name] = st.text_area("Edit", txt, key=f"ed_{sel}_{it.name}", height=110, label_visibility="collapsed")
                    if it.limit:
                        u = drafter._count(edited[it.name], it.unit)
                        (st.success if u <= it.limit else st.error)(f"{u}/{it.limit} {it.unit}" + ("" if u <= it.limit else "  over the limit"))
            res2 = dict(res); res2["draft"] = edited
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "draft.docx"; drafter.to_docx(n, profile, res2, str(p))
                d1, d2 = st.columns(2)
                d1.download_button("⬇ Download Word file", p.read_bytes(), file_name=f"{sel}_draft.docx", width="stretch")
                d2.download_button("⬇ Download Markdown", drafter.to_markdown(n, profile, res2), file_name=f"{sel}_draft.md", width="stretch")

# ================================================================= 4 COMPARE
elif page == PG[3]:
    st.markdown("### Compare calls side by side")
    pick = st.multiselect("Choose 2 or 3 calls", ids, default=["SERB-SRG", "SERB-ECRA", "ICMR-FIW-2026"], format_func=lambda i: titles[i], max_selections=3)
    if len(pick) < 2: st.info("Pick at least two calls.")
    else:
        data = {}
        for i in pick:
            n = idx.by_id[i]; r = check(n, profile, today); dd = n.deadline_date()
            data[i] = {"Agency": n.agency, "Deadline": n.deadline_text if n.deadline else "not stated",
                       "Days left": (dd - today).days if dd else "n/a", "Budget": n.budget, "Duration": n.duration,
                       "Your verdict": kind(r["verdict"])[1], "Rules passed": sum(1 for x in r["results"] if x.status == "PASS"),
                       "Rules failed": len(r["blockers"]), "Proposal sections": len([x for x in n.proposal_format]), "Documents to attach": len(n.attachments),
                       "Themes": n.themes[:150]}
        st.dataframe(pd.DataFrame(data).astype(str), width="stretch")
        st.caption("Sources: " + " · ".join(f"[{i}]({idx.by_id[i].source})" for i in pick))

# ================================================================= 5 ASSISTANT
elif page == PG[4]:
    st.markdown("### 💬 Ask the Grant Assistant")
    st.caption("Answers come only from the call records and cite their source. If it is not in the records, the assistant says so.")
    cols = st.columns(3)
    for i, s in enumerate(chatbot.SUGGESTIONS):
        cols[i % 3].button(s, key=f"sg{i}", on_click=chat_reply, args=(s,), width="stretch")
    if not st.session_state["chat"]:
        st.info("Pick a suggested question above or type your own below. Try: *Am I eligible for SRG?*")
    for role, text in st.session_state["chat"]:
        with st.chat_message(role): st.markdown(text)
    if msg := st.chat_input("Ask about deadlines, budgets, eligibility, documents, sections..."):
        chat_reply(msg); st.rerun()
    if st.session_state["chat"]: st.button("🗑 Clear chat", on_click=lambda: st.session_state.update(chat=[]))

# ================================================================= 6 EVALUATION
elif page == PG[5]:
    ev = get_eval(); e, t, dr, c = ev["eligibility"], ev["retrieval"], ev["drafting"], ev["chatbot"]
    st.markdown("### 📊 Performance evaluation")
    st.caption("Test cases were written by hand from the call wording, so expected answers do not come from the program. The test set is small; read results as a prototype check, not a benchmark.")
    m = st.columns(4)
    m[0].metric("Eligibility accuracy", f"{e['correct']}/{e['n']}", f"{100*e['correct']/e['n']:.0f}%")
    m[1].metric("Retrieval hit@1", f"{t['hit1']}/{t['n']}"); m[2].metric("Retrieval MRR", t["mrr"])
    m[3].metric("Chatbot answers correct", f"{c['content_ok']}/{c['n']}")
    # ---- overall scorecard, confusion matrix, latency
    import time as _t
    labels = sorted({r["expected"] for r in e["rows"]} | {r["got"] for r in e["rows"]})
    cm = pd.DataFrame(0, index=[f"Expected {l}" for l in labels], columns=[f"Predicted {l}" for l in labels])
    for r in e["rows"]: cm.loc[f"Expected {r['expected']}", f"Predicted {r['got']}"] += 1
    prf = []
    for l in labels:
        tp = sum(1 for r in e["rows"] if r["expected"] == l and r["got"] == l); fp = sum(1 for r in e["rows"] if r["expected"] != l and r["got"] == l); fn = sum(1 for r in e["rows"] if r["expected"] == l and r["got"] != l)
        p = tp/(tp+fp) if tp+fp else 0.0; rc = tp/(tp+fn) if tp+fn else 0.0; f1 = 2*p*rc/(p+rc) if p+rc else 0.0
        prf.append({"Verdict class": l, "Cases": tp+fn, "Precision": round(p, 2), "Recall": round(rc, 2), "F1": round(f1, 2)})
    macro_f1 = sum(x["F1"] for x in prf)/len(prf)
    t0 = _t.perf_counter()
    for _i in range(5):
        _ = chatbot.answer("What is the deadline for SRG?", idx, profile, today)
    chat_ms = (_t.perf_counter()-t0)/5*1000
    comps = {"Eligibility accuracy": e["correct"]/e["n"], "Retrieval hit@3": t.get("hit3", t["hit1"])/t["n"], "Chatbot correctness": c["content_ok"]/c["n"], "Draft compliance (v2 final)": dr["v2"]["final"]/100}
    overall = 100*sum(comps.values())/len(comps)
    st.markdown("#### Overall performance score")
    o = st.columns([1, 3]); o[0].metric("Overall score", f"{overall:.1f} / 100", help="Mean of the four component scores on the right")
    o[1].dataframe(pd.DataFrame({"Component": list(comps), "Score %": [round(100*v, 1) for v in comps.values()]}), hide_index=True, width="stretch")
    st.caption(f"Average chatbot response time: {chat_ms:.2f} ms (no LLM, local). Macro F1 of eligibility verdicts: {macro_f1:.2f}. Small hand-written test set, so scores are a prototype check, not a benchmark.")
    st.markdown("#### Evaluation matrix: eligibility verdicts (confusion matrix)")
    st.dataframe(cm, width="stretch")
    st.dataframe(pd.DataFrame(prf), hide_index=True, width="stretch")
    st.markdown("#### Drafting prompt: v1 initial vs v2 optimized (average over all 8 calls)")
    cmp = pd.DataFrame({"v1 initial": dr["v1"], "v2 optimized": dr["v2"]}).rename(index={"first_pass": "First-pass compliance %", "final": "Final compliance %", "rounds": "Review rounds",
                        "duplication": "Repetition between sections (lower is better)", "keyword_noise": "Noise words in keywords (lower is better)", "limit_violations_final": "Limit violations after review"})
    st.dataframe(cmp, width="stretch")
    tab1, tab2, tab3, tab4 = st.tabs(["Eligibility cases", "Retrieval queries", "Draft quality per call", "Chatbot questions"])
    tab1.dataframe(pd.DataFrame(e["rows"]), hide_index=True, width="stretch")
    tab2.dataframe(pd.DataFrame(t["rows"]), hide_index=True, width="stretch")
    tab3.dataframe(pd.DataFrame(dr["per_call"]["2"] if "2" in dr["per_call"] else dr["per_call"][2]), hide_index=True, width="stretch")
    tab4.dataframe(pd.DataFrame(c["rows"]), hide_index=True, width="stretch")

# ================================================================= 7 RESPONSIBLE AI
elif page == PG[6]:
    st.markdown("### 🛡️ Responsible AI")
    items_ = [("Bias and fairness", "Gender and social category are used only where a call's own rules use them (for example the age relaxation for women and SC/ST/OBC/PwD, or women-only calls). They never change ranking. Every verdict lists its rules so unfair outcomes can be seen and challenged."),
              ("Privacy", "The researcher's details live only in the browser session. Nothing is saved to disk or sent to a server, and the default pipeline needs no internet or LLM. If an LLM is enabled, only the research idea text is sent."),
              ("Hallucination mitigation", "Eligibility and chat answers come from stored call records, not from model memory. The assistant cites the source of each answer and says 'not in my records' instead of guessing. Drafts never invent results, numbers or citations; gaps are marked [PI TO WRITE] or [PI TO CONFIRM], and attachments are never generated."),
              ("Explainability", "Each verdict shows rule by rule what passed, failed or needs a human check, with the reason. Near misses name the exact failing rule, and the what-if panel shows what would change the result."),
              ("Safety and accountability", "The tool advises; the researcher decides and submits. Every call links to its official page, records are marked as paraphrased, and a banner asks users to verify before applying. A review loop checks structure, never scientific quality."),
              ("Known limits", "Only 8 calls, hand-structured. Eligibility covers about a dozen rule types and flags the rest for manual reading. Draft text is a scaffold. No fairness audit with real applicants has been done yet.")]
    for h, t in items_: st.markdown(f'<div class="rai"><b>{h}</b><br>{t}</div>', unsafe_allow_html=True)
    ev = get_eval()
    st.markdown("#### Live check")
    a, b = st.columns(2)
    a.metric("Chat answers that cite a source or decline", f"{ev['chatbot']['cited']}/{ev['chatbot']['n']}"); b.metric("Draft limit violations after review", ev["drafting"]["v2"]["limit_violations_final"])

# ================================================================= 8 ABOUT
else:
    st.markdown("### How it works")
    cols = st.columns(5)
    steps = [("① Discovery agent", "Searches call records (TF-IDF over section chunks), filters by deadline and agency."), ("② Eligibility agent", "Tests each call rule against your profile and explains every pass, fail and near miss."),
             ("③ Guideline compiler", "Turns the call's format rules into a checklist of sections, limits and attachments."), ("④ Drafting + review agent", "Writes a draft, checks it against the checklist, fixes gaps, repeats."),
             ("⑤ Assistant", "Answers questions from the records with citations; refuses to guess.")]
    for col, (h, t) in zip(cols, steps): col.markdown(f'<div class="step"><b>{h}</b><br><span class="meta">{t}</span></div>', unsafe_allow_html=True)
    st.markdown("#### Knowledge base (real calls, paraphrased)")
    st.dataframe(pd.DataFrame([{"Call": n.title, "Agency": n.agency, "Deadline": n.deadline_text if n.deadline else "not stated", "Status": n.status(today), "Rules": len(n.eligibility),
                                "Format items": len(n.proposal_format), "Source": n.source} for n in idx.notices]), hide_index=True, width="stretch",
                 column_config={"Source": st.column_config.LinkColumn("Source")})
    st.markdown("#### Current limits")
    st.markdown("- 8 calls only, structured by hand; PDF parsing is not automatic yet.\n- Retrieval is keyword-based (TF-IDF); embeddings are planned.\n- Eligibility covers about a dozen rule types; others are flagged for you to read.\n- Drafting is a template unless an LLM key is set (`GRANT_LLM=gemini` + `GEMINI_API_KEY` (or `GRANT_LLM=anthropic`)).")
