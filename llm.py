"""Optional LLM plug-in (off by default). The prototype works fully without it (template drafting).
Gemini:     set GRANT_LLM=gemini      and GEMINI_API_KEY=...   (GRANT_MODEL optional, default below)
Anthropic:  set GRANT_LLM=anthropic   and ANTHROPIC_API_KEY=...
Any error or missing key falls back to the template draft, so the app never breaks."""
import json, os, urllib.request

PROMPT_V1 = "Write the '{name}' section {limit} of a proposal for '{title}'. Researcher idea: {idea}."
PROMPT_V2 = (
    "You are drafting one section of a research grant proposal. Section: '{name}' {limit}. Call: '{title}'.\n"
    "Researcher idea (the only source of facts): {idea}\n"
    "Rules: stay within the limit; use only facts in the idea; never invent results, numbers or citations; "
    "write [PI TO CONFIRM: what is needed] wherever a fact is missing; do not repeat text used in other sections; "
    "plain academic English, no marketing language."
)
GEMINI_DEFAULT_MODEL = "gemini-3.7-flash"   # check the current model name in Google AI Studio; override with GRANT_MODEL

def provider():
    p = os.environ.get("GRANT_LLM", "").lower()
    if p == "gemini" and os.environ.get("GEMINI_API_KEY"): return "gemini"
    if p == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"): return "anthropic"
    return None

def available():
    return provider() is not None

def _gemini(prompt):
    model = os.environ.get("GRANT_MODEL", GEMINI_DEFAULT_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

def _anthropic(prompt):
    import anthropic
    msg = anthropic.Anthropic().messages.create(model=os.environ.get("GRANT_MODEL", "claude-sonnet-5-5"), max_tokens=700,
                                                messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text

def draft_section(name, limit_text, idea, notice_title):
    p = provider()
    if not p: return None
    prompt = PROMPT_V2.format(name=name, limit=limit_text, title=notice_title, idea=idea)
    try:
        return _gemini(prompt) if p == "gemini" else _anthropic(prompt)
    except Exception:
        return None   # fall back to the template draft
