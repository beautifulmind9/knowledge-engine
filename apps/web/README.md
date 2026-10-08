# Knowledge Engine web interface

The active frontend uses HTML, CSS, and browser JavaScript modules. FastAPI serves `index.html` at `/` and assets under `/static`; no npm installation or build is required.

Screens: Library, Source detail, Knowledge, Workshop, Saved outputs, Output/history, and Data & usage. The shared `api()` helper handles JSON, uploads, and readable API failures. All source/model text is inserted with `textContent`, not interpreted as HTML.

Run the project with `bash scripts/run.sh` from the repository root. Seed original sample material with `.venv/bin/python scripts/seed_demo.py` while the app runs.

Accessibility provisions include semantic controls, nested labels, a skip link, live status feedback, progress labels, busy state, focus outlines, and responsive CSS. These still need an actual browser/mobile acceptance pass; they are not an accessibility certification. Use `docs/beta_test_checklist.md` to record that review.

Local mode remains accessible without a password. Hosted mode uses one shared private-beta password and signed browser sessions; the login page needs only the shared stylesheet. The shared `api.js` transport adds session-bound CSRF headers to unsafe same-origin requests, including the enhancement layer, while retaining Workshop payload decorators. A POST Sign out action clears browser cookies. Manual JSON import is an advanced path; ordinary AI processing and saved-output revision use forms.

Frontend tests: `node --test --test-isolation=none apps/web/tests/*.test.mjs` from the repository root. All request tests use mocks.
