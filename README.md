# Research Grant Assistant (PS 52 prototype, Review 2)
Hackathon PS 52 prototype. Partially working prototype: discovery, eligibility, guideline checklist, draft-and-review loop.

## Run
    pip install -r requirements.txt
    streamlit run app.py          # web UI at http://localhost:8501
    python cli.py discover --profile data/profiles/asha.json --today 2026-11-25
    python cli.py check --profile data/profiles/ravi.json --notice SERB-ECRA
    python cli.py checklist --notice SERB-SRG
    python cli.py draft --profile data/profiles/asha.json --notice SERB-SRG --out outputs/demo
    python -m pytest -q tests

## Features (final)
8 pages: Find calls (verdicts, deadline alerts, CSV and .ics export), Eligibility (rule by rule, what-if), Proposal (draft and review loop v1/v2, editable, Word/Markdown export), Compare, Assistant (grounded chat, also as a popup on every page), Evaluation, Responsible AI, About.
Run `python eval.py` for the evaluation report; `python -m pytest -q tests` (15 tests).

## Data
`data/notices/*.txt`: 8 real Indian funding calls, paraphrased from official pages (source URL in each file, retrieved 2026-11-25). Verify against the original before relying on them. Add more by copying the file format.

## Optional LLM (Gemini or Anthropic)
Windows (PowerShell):  $env:GRANT_LLM="gemini"; $env:GEMINI_API_KEY="your-key"; py -m streamlit run app.py
Optional: $env:GRANT_MODEL="<model name from Google AI Studio>". Without a key, or on any API error, the template draft is used. Not yet tested with a real key.

## Known limits
Rule-based eligibility covers common clauses only; others are listed as [check]. Retrieval is TF-IDF (no embeddings yet). PDF ingestion of raw notices is not implemented; notices were hand-structured. Web UI is a first version (no login, no saved sessions).
