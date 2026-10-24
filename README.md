# BrandGuard — Round 2 MVP
**Governance, not gatekeeping.** An evidence-cited, human-controlled brand-governance prototype for Team Vertex.

## Run locally

### Windows
1. Install Python 3.10+ and enable **Add Python to PATH**.
2. Extract this ZIP to a folder.
3. Double-click `run_windows.bat` (first run installs the dependencies).
4. Open http://127.0.0.1:8000 in your browser.
5. API documentation: http://127.0.0.1:8000/docs

### macOS / Linux
```bash
chmod +x run.sh
./run.sh
```
Then open http://127.0.0.1:8000.

The application uses a local SQLite database at `data/brandguard.db`, created and seeded on first startup. To reset demo data, stop the server and delete that database file before restarting.

## Working features
- Dashboard with live review counts, finding counts, rules and expired claim indicators.
- Create a text review with channel and target audience.
- Deterministic checks for preferred terminology, prohibited phrases, absolute promises, quantitative/ranking claims and expired registered claims.
- Each finding links to a rule ID or claim ID, includes rationale, severity, screening confidence, suggested wording and decision controls.
- Accept/reject a finding, record “needs human check”, and edit/save replacement wording.
- Approval workflow blocks approval while findings remain open; request changes, submit and reopen actions are audited.
- Comments, timestamps, version field and audit trail.
- Add approved claims with evidence source, owner and expiry; add guideline rules.
- Governance insights with issue-category counts and a cautious guideline-ambiguity signal.
- Image screening for dimensions, average colour/luminance, theoretical contrast against average colour, and missing alt text; JSON export.
- Export review records and insights as JSON.
- Responsive UI, local processing disclosure and sample records for an immediate demo.

## Important implementation disclosures
- This is a functional MVP, not a production-secure multi-user service. Demo identity fields are not authentication. Do not expose it publicly with confidential brand material.
- The checker is deterministic rule-based logic; no external LLM, Groq, Ollama or LangChain call is configured. “Confidence” is a heuristic screening signal, not a calibrated model probability or measured accuracy.
- Image analysis is only a screening aid. Average-colour contrast is not a WCAG compliance verdict; it does not yet detect text regions, compare approved logos or perform OCR.
- No automatic rewrite or publication occurs. A reviewer remains responsible for decisions.
- The proposed architecture in the Round 1 PDF mentions React/Tailwind, FastAPI, PostgreSQL/SQLite, retrieval and an LLM. This self-contained Round 2 demo uses FastAPI + a plain JavaScript frontend + SQLite to keep local setup simple. Document this implementation change honestly in the updated PDF.

## API overview
- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/reviews`, `POST /api/reviews`, `GET /api/reviews/{id}`
- `POST /api/reviews/{id}/findings/{finding_id}/decision`
- `POST /api/reviews/{id}/workflow`, `POST /api/reviews/{id}/comments`
- `POST /api/rules`, `POST /api/claims`
- `POST /api/visual-check`
- `GET /api/export/{id}`

## Round 3 improvement roadmap
1. **Claim Ledger v2:** source-document ingestion, semantic matching, expiry reminders and claim-owner review.
2. **Guideline Ambiguity Radar:** track decision/override patterns across labelled reviews and recommend rule clarifications with manager approval.
3. **Visual and accessibility engine:** OCR/text-region contrast, approved-logo matching, colour palette comparison and structured alt-text review.

## Suggested demo path
1. Open Overview and point out the seeded sample reviews.
2. Click New review → Try an example → Review against brand rules.
3. Open the resulting review; show the cited rule/fact and confidence disclosure.
4. Accept or reject findings, add a comment, then approve only after all findings have a decision.
5. Open Claim ledger and Brand guidelines; add a test claim/rule.
6. Open Governance insights and Visual & accessibility; upload a sample image with and without alt text.
7. Export the review JSON and show the audit trail.

## Claim expiry regression tests

The Claim Ledger review check compares a claim's expiry date with the current date, even if its stored status was accidentally left as `active`. A malformed or missing expiry date is flagged for human verification when the registered claim wording appears in a draft.

Run the built-in regression tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

The tests cover stale evidence with an `active` status, a future-dated active claim, an explicitly expired claim, and an invalid expiry date.
