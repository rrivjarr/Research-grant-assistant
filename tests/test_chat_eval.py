import sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import eval as ev, chatbot
from retrieval import Index

def test_eval_thresholds():
    r = ev.run()
    assert r["eligibility"]["correct"] == r["eligibility"]["n"]
    assert r["retrieval"]["hit3"] == r["retrieval"]["n"]
    assert r["chatbot"]["content_ok"] == r["chatbot"]["n"]
    assert r["drafting"]["v2"]["duplication"] < r["drafting"]["v1"]["duplication"]

def test_chat_declines_unknown():
    a = chatbot.answer("What is the capital of France?", Index(), ev.P(), dt.date(2026, 11, 25))
    assert a["intent"] == "unknown" and "not in my records" in a["text"].lower()

def test_nmc_compound_clause():
    from eligibility import check
    r = check(Index().by_id["ICMR-NMC-MEDEDU"], ev.P(), dt.date(2026, 8, 1))
    assert r["verdict"].startswith("NOT ELIGIBLE")

def test_llm_off_by_default_and_gemini_request(monkeypatch):
    import llm, io, json
    monkeypatch.delenv("GRANT_LLM", raising=False)
    assert llm.draft_section("Summary", "(max 100 words)", "idea", "Call") is None
    monkeypatch.setenv("GRANT_LLM", "gemini"); monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    seen = {}
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def fake(req, timeout=0):
        seen["url"] = req.full_url; seen["key"] = req.headers.get("X-goog-api-key"); seen["body"] = json.loads(req.data)
        return R(json.dumps({"candidates": [{"content": {"parts": [{"text": " Drafted text "}]}}]}).encode())
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake)
    assert llm.draft_section("Summary", "(max 100 words)", "my idea", "Call") == "Drafted text"
    assert seen["key"] == "test-key" and seen["url"].endswith(":generateContent") and "my idea" in seen["body"]["contents"][0]["parts"][0]["text"]
    def boom(req, timeout=0): raise OSError("network down")
    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    assert llm.draft_section("Summary", "", "idea", "Call") is None
