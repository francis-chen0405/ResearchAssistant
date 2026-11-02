# ResearchAssistant backend

Install from the repository with `python -m pip install ./backend` or
`python -m pip install -e "./backend[dev]"`. Run `researchassistant --help`
from any working directory. The runtime, API, agents, providers, prompts and PDF
font are owned by `src/researchassistant/`. Historical import namespaces under
`src/` are installed facades. See [the root guide](../README.md),
[current status](../docs/project/STATUS.md), [API notes](src/researchassistant/api/README.md)
and [test map](../tests/README.md) for workspace usage and verification.

Record a reviewed study opening with `researchassistant record-report-review DATABASE REVIEW.json`.
The JSON follows `V2ReportStudyReview` in `evidence/report_review.py`. It records the reviewer,
selection rationale, exact admitted assertion references, study identifiers, and captured
publication provenance. Authoritative captures must already exist in acquisition storage;
identifiers and metadata must match their captured text and the admitted reading passage.
The command validates before inserting an immutable review artifact. New reports and exports
use that artifact. Publication-only reviews may omit assertions. Small evidence sets with
verified publication identities and consistent admitted statements receive an exhaustive,
extractive opening, including every recorded limitation. Other runs retain the explicit
synthesis fallback; publication identity never establishes independent study identity.
New copies, downloads, and backend exports use one canonical reading aid from the evidence
projection. The original released brief and its hash remain unchanged.
