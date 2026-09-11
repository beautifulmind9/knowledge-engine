# Knowledge Engine workspace

The first usable workspace is a responsive, dependency-free HTML/CSS/JavaScript client served by FastAPI at `/`. It calls real same-origin endpoints for libraries, uploads, processing, evidence review, and saved workshops; browser storage is not used for research data.

Run the API using the repository README. No separate frontend build or server is needed. The planned React/Next.js migration remains optional future work; the API boundary is preserved.

The three views are Library, Knowledge, and Workshop. Source text and imported/generated text are escaped or assigned using `textContent`/textarea values, never executed as HTML. There are empty, error, busy, and unsaved-output states. Styling supports narrow screens without changing the workflow.
