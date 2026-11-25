import os, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
from streamlit.testing.v1 import AppTest
PG = ["🔎 Find calls", "✅ Eligibility", "📝 Proposal", "⚖️ Compare", "💬 Assistant", "📊 Evaluation", "🛡️ Responsible AI", "ℹ️ About"]

def _app(): return AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()

def test_home_runs():
    at = _app(); assert not at.exception; assert len(at.metric) == 4

def test_all_pages_render():
    at = _app()
    for p in PG:
        at.session_state["page"] = p; at.run(); assert not at.exception, p

def test_draft_runs():
    at = _app(); at.session_state["page"] = PG[2]; at.session_state["sel"] = "SERB-SRG"; at.run()
    [b for b in at.button if "Run draft" in b.label][0].click(); at.run()
    assert not at.exception
    assert any(m.label == "Final score" and m.value == "100%" for m in at.metric)

def test_chat_page_suggestion_answers():
    at = _app(); at.session_state["page"] = PG[4]; at.run()
    [b for b in at.button if "deadline for the ICMR" in b.label][0].click(); at.run()
    assert not at.exception
    assert any("30 Nov 2026" in m.value for m in at.markdown)
