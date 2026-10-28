# cvreview — Candidate Document Review Pipeline

Evidence-first, criteria-authorised, human-gated review of candidate
application packets. Architecture and implementation plan:
[`docs/candidate-review-pipeline-plan.md`](docs/candidate-review-pipeline-plan.md).

**Status:** Increments 1 + 3 complete — packet ingestion & provenance, plus the
deterministic verification core (plan §28).

## Privacy

`data/` contains real candidate documents and derived artifacts.
**It is gitignored and must never be committed, copied into development
fixtures, or pasted into debugging tools** (plan §20). Fixtures for tests
must be synthetic or redacted.

## Setup (VS Code)

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

Open the folder in VS Code and select `.venv` as the interpreter.
`Tesseract OCR` must be installed (auto-detected at
`C:\Program Files\Tesseract-OCR\tesseract.exe` or via PATH).

## Usage

```powershell
# ingest every PDF in data/raw
.venv\Scripts\cvreview ingest-folder

# ingest one packet
.venv\Scripts\cvreview ingest data\raw\808_5422_Jacob_Thomson.pdf
```

Outputs per packet, under `data/packets/<packet_id>/`:

- `packet.json` — the PacketModel: page types, documents, duplicate groups,
  warnings, config versions
- `pages/page_NN.png` — rendered pages (provenance anchors for review UI)
- `audit.jsonl` — append-only audit events (plan §19)

## Increment 1 scope

Deterministic only — no LLM calls:

- page classification (form / CV / cover letter / divider / blank / no-data /
  fragment-continuation), corpus-validated on 39 pages
- text-layer capture **and** OCR capture with word-level bounding boxes and
  confidence — uniform provenance either way
- near-duplicate document detection (text similarity + image hashing)
- quote resolution: verbatim quote → char span → word boxes (invariant I1)
- audit trail events for every page and decision

## Tests

```powershell
.venv\Scripts\python -m pytest
```

Unit tests are synthetic; the integration test runs against `data/raw/`
when candidate packets are present and asserts the full corpus ground truth.
