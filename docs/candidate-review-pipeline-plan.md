# Candidate Document Review Pipeline — Architecture & Implementation Plan

**Status:** Planning (no production code)
**Version:** v0.1 (draft for technical review)
**Date:** 2026-10-23
**Prepared from:** 7 supplied candidate application packets (`808_5422` … `808_9754`)
**Missing authorised inputs:** job specification, assessment framework (see Open Questions)

---

## 1. Executive Summary

We propose an **evidence-first, criteria-authorised, human-gated** review pipeline for candidate application packets. The design is driven by direct inspection of the supplied corpus, which revealed three facts that dominate the architecture:

1. **The documents are image-based.** Every packet is an ATS (applicant tracking system) export: page 1 is a text-layer form ("Applicant Summary"), while all CV and cover-letter pages are raster images with no usable text layer. **OCR is not an edge case — it is the primary ingestion path**, and every downstream capability (traceability, verification, fairness) depends on preserving OCR word-level coordinates.
2. **Packets are messy containers, not clean documents.** They contain divider pages, blank pages, "No data available" pages, near-duplicate CVs (candidate `808_6934`: the CV appears twice in different renderings), near-duplicate cover letters (candidate `808_9411`), a CV fragment orphaned by a page break (`808_7533`), and a truncated line at a page boundary (`808_7949`). A **packet-splitting / page-classification stage** must precede extraction.
3. **No job specification or assessment framework was supplied.** The system must therefore treat **criteria authoring as its own versioned pipeline stage (Stage 0)** — parsing an authorised Job Specification + Assessment Framework into a machine-readable Criteria Register — and must refuse to score anything not in that register. The target role ("Aerodynamic Design Industrial Placement, Mercedes-AMG PETRONAS F1") is inferable from the documents, but **we do not invent criteria from it**.

The pipeline is:

```
Stage 0  Authorised inputs: job spec + assessment framework → Criteria Register (versioned)
Stage 1  Packet ingestion: page classification, OCR with coordinates, provenance model
Stage 2  Extraction: schema-constrained evidence items with verbatim quotes + locations
Stage 3  Verification & normalisation: deterministic checks + controlled vocabularies
Stage 4  Criteria mapping: evidence → authorised criteria (quotes mandatory)
Stage 5  Assessment: per-criterion evidence classification with rationale
Stage 6  Scoring: deterministic rubric engine (no LLM), weights from config only
Stage 7  Human review: report with drill-down to source, recorded overrides
```

LLMs are used only where semantic interpretation is genuinely required (OCR error correction is NOT one of them; extraction, section classification, mapping, and assessment are). Scoring, weight application, date arithmetic, duplicate detection, and audit logging are deterministic code. All LLM stages emit schema-validated JSON; invalid output is quarantined, never silently propagated. Uncertainty is represented categorically and surfaced to the reviewer — never folded invisibly into a score.

---

## 2. Requirements and Assumptions

### 2.1 Restated objective

Build a **decision-support system** that reviews candidate application packets against an authorised job specification and assessment framework, producing per-criterion, evidence-backed assessments and (where configured) scores, fully traceable from score back to pixel coordinates in the original PDF, for final judgement by a human reviewer.

### 2.2 Hard requirements (from the brief)

- R1 Traceability: score → assessment → criterion → evidence → original document location.
- R2 Criteria authorisation: no requirement may be assessed that is not in the authorised framework.
- R3 Evidence-first: extraction must not judge; assessment must cite evidence.
- R4 Distinguish: stated / normalised / inferred information; minimise category 3.
- R5 Distinguish "no evidence found" from "evidence shows criterion not met".
- R6 Protected characteristics and proxy signals must not be used or inferred.
- R7 Human-in-the-loop: decision support only, with recorded overrides.
- R8 Structured, validated LLM outputs; invalid output detected, not propagated.
- R9 Full auditability with versioned prompts, schemas, criteria, rubrics, models.
- R10 Personal data: minimisation, retention, deletion, no leakage into dev environments or logs.

### 2.3 Assumptions (each is challenged in §27 Open Questions)

- A1. Packets will continue to arrive in this ATS export shape (summary form + images), but with variable inner documents. The design does not depend on it: the page classifier treats any page as unclassified until proven otherwise.
- A2. One candidate = one packet; candidate identified by the numeric ATS ID (e.g. `808_5422`), not by name.
- A3. Assessment framework will provide, per criterion: description, essential/desirable, weighting (optional), evidence expectation, and scoring rule. **None supplied yet.**
- A4. An approved LLM endpoint exists or will exist (tenancy-approved; see §20 — this is a privacy-critical open question).
- A5. Throughput is tens-to-hundreds of packets per campaign, not millions — favours simple, inspectable batch architecture over distributed infrastructure.
- A6. "Verification" means verification **against the submitted documents**; no external credential-checking service is in scope (explicitly noted in the brief).

---

## 3. Analysis of Supplied Example Documents

### 3.1 Corpus overview

7 packets, 39 pages total, 7 candidates. All are ATS exports for the same role (referenced in cover letters: "Aerodynamic Design Industrial Placement" at Mercedes-AMG PETRONAS Formula One Team; candidate `808_6934`'s duplicate CV carries the header "Aerodynamics Industrial Placement (Ref: 804)"). All page-1 forms say `Status: Shortlisted`, `Type: External Candidate`, `How did you learn about this job?` (LinkedIn / College/School / CV).

| Candidate (file ID) | Pages | Packet contents | CV layout | Notable features |
|---|---|---|---|---|
| `808_5422` Jacob Thomson | 3 | Form; 1-page CV; "No data available" page | Dense serif, right-aligned dates, pipe-separated skills list | **Cover letter missing** (divider present, no letter). In-packet promotion narrative (Junior→Senior→Technical Lead within one year) with explicit dates |
| `808_6934` Samuel Hayes | 7 | Form; CV (p2); sparse CV continuation (p3); "Cover Letter" divider (p4); **near-duplicate CV** (p5, with job-ref header); cover letter (p6); blank (p7) | Large sans-serif, bold inline claim sentences | **CV appears twice in different renderings** (formatting/content drift risk). Letter reveals non-traditional route (Access to HE Diploma) **not present in the CV** |
| `808_7533` Sam Spencer | 6 | Form; 2-page CV; "Cover Letter" divider (p4); letter (p5); blank (p6) | Arial, underlined headings, italic date lines above roles | **Orphaned date "June 2024" at top of p3** — the date for the BAE Systems item was separated from its heading by the page break. Includes non-technical work (Wimbledon host, football mascot) and "full UK driving license" |
| `808_7949` Sajana Pathirana | 6 | Form; 2-page CV; near-blank p4; letter (p5); blank (p6) | Nested bullet hierarchy, italic per-project "Skills:" lines | **Explicit self-declared proficiency matrix** ("Onshape – Advanced, 6+ years"; "CATIA V5 – Basic, 10-hour course"). **Line truncated at page boundary** ("Hiking, including multi-day treks across the Founda—"). Letter addresses recruiters by name and discloses a previous assessment-centre rejection |
| `808_9158` Benjamin Hall | 5 | Form; 1-page CV; letter (p4); blank (p5) | Compact, ALL-CAPS blue headings, inline module grades | Letter contains **nationality / right-to-work / family-origin detail** (fairness-sensitive — must be excluded from assessment). Contains an **adaptability claim** ("adapting to a new CAD software like CATIA won't be a problem") — stated, not evidenced |
| `808_9411` Simon Ram | 7 | Form; 2-page CV; letter (p4); letter divider (p5); **near-duplicate letter** (p6); blank (p7) | Traditional academic, centred ALL-CAPS headers, education before experience, year-by-year grades | Software lists use different names than prose ("CATIA 3DX" in list vs "CATIA 3DEXPERIENCE" in prose). Cover letter appears **twice**, the second copy behind its own divider page (p5) |
| `808_9754` Henry Holme | 5 | Form; 2-page two-column CV (fragment on p3); letter (p4); blank (p5) | **Two-column: blue sidebar** (contact/profile/education/hobbies/proficiencies) + main column | **Coloured background + small-caps + unusual glyphs ("◇") — hardest OCR case in corpus.** CV overflows onto p3 leaving a single orphaned line. Inline metrics ("1.34C_L (66%) increase") |

### 3.2 Structural findings with architecture consequences

| # | Observation | Consequence for design |
|---|---|---|
| 1 | CV/letter pages are images; only the ATS form has a text layer | OCR is the main path; text-layer path is a cheap deterministic win for page 1 |
| 2 | Page-1 form is label/value pairs with repeated labels ("Email" twice) | Deterministic form extraction (no LLM); dedup of repeated fields |
| 3 | Divider pages ("Cover Letter" banner) and blank pages | Page classifier must recognise non-content pages and drop them from evidence flow |
| 4 | Near-duplicates (CV ×2 for `808_6934`; letter ×2 for `808_9411`) | Near-duplicate detection must operate **before** evidence extraction to avoid double-counting evidence; duplicates are *merged*, not scored twice |
| 5 | Page-break artifacts: orphaned date (`808_7533`), orphaned fragment line (`808_9754`), truncated sentence (`808_7949`) | Section identification must work **across page boundaries**; extraction must be allowed to flag "split item" rather than inventing a fact |
| 6 | Skills named inconsistently within and across CVs (STAR-CCM+ / Star CCM+ / StarCCM+; CATIA 3DX / CATIA 3DEXPERIENCE / CATIA V5; Ansys / ANSYS; SimScale) | Versioned **skill alias registry** (deterministic normalisation) + LLM-assisted candidate aliases queued for human curation, never auto-added |
| 7 | Self-declared proficiency scales ("Advanced / Intermediate / Basic", "6+ years") | Proficiency levels are *candidate claims*: capture as claim metadata with source; scoring rubric decides how much weight self-ratings get — that decision belongs in the authorised framework, not the code |
| 8 | Cover letters contain material facts absent from CVs (Hayes's Access route; Hall's module list lives only in CV; Ram's karting series only in letter) | Extraction must cover **all** substantive documents, not CV only; criteria mapping may cite letters |
| 9 | Fairness-sensitive content present (nationality, family origin, addresses, named recruiters, assessment history, hobbies, driving licence) | Dedicated **sensitive-content redaction/tagging stage** before mapping/assessment; these items are stored (for traceability) but excluded from criteria mapping inputs |
| 10 | Every CV quantifies achievements ("49% downforce", "18% efficiency", "£300,000 raised", "30% mass saving") | Numbers are attractive to extract but are self-reported; evidence model records `quantified: true` but the *weighting* of quantified vs unquantified claims is a rubric decision |
| 11 | Dates overlap and nest (roles within teams, "2025 - present", "February 2026 - Present", month-precision mixed with year-precision) | Date normalisation to (earliest, latest, precision) intervals; chronology checks operate on intervals, not instants |
| 12 | One candidate has no cover letter; several have blank/empty letter sections | Absence of a letter must **not** be an assessment outcome; it is `NOT_SUBMITTED` packet metadata |

### 3.3 Extractability classification (informed by the corpus)

- **Deterministically extractable:** ATS form fields; page classification (mostly); near-duplicate detection; date ranges via pattern library (most dates in corpus are well-formed); skill-alias normalisation; hyperlink/URL presence; word-level OCR provenance.
- **Semantic interpretation required (LLM, schema-constrained):** section identification in novel layouts; role/organisation splitting ("UBRacing (Formula Student) – SSB Design Engineer, July 2026 - Present"); responsibility/achievement statements as discrete evidence items; project descriptions; claim-vs-evidence character; synonym mapping beyond the alias registry.
- **Unsuitable for assessment (must be tagged and excluded):** contact details; addresses; nationality/right-to-work (`808_9158`); names of recruiters; hobbies (unless a criterion explicitly covers relevant interests — the framework decides); candidate's own proficiency self-ratings (captured, weighted only if the rubric says so).

### 3.4 Likely extraction failure modes observed or predicted

1. OCR mis-reads on the Holme sidebar (small caps, coloured background, glyphs) — mitigations: per-word OCR confidence, dual-engine cross-check on low-confidence words, and **"NOT_ASSESSABLE" outcome** when OCR quality is too low rather than guessing.
2. Two-column reading-order errors (sidebar interleaved into main column).
3. Page-break splits treated as two facts or zero facts.
4. Near-duplicate documents yielding double-counted evidence.
5. Hyperlink labels ("Design Portfolio", "Engineering Portfolio") pointing to work that is **not in the packet** — the system must record "evidence exists behind a link we cannot see" as `NOT_ACCESSIBLE`, never as positive evidence.
6. Names/organisations mis-OCR'd producing phantom skills ("Star-CCM+" vs "Star-CCM-").

---

## 4. Key Risks and Design Constraints

**Technical**
- T1 OCR quality bounds everything downstream; errors are silent unless provenance-checked. → word-level confidence + quote-verification against OCR text + human sampling.
- T2 LLM structured-output failures. → pydantic validation at every boundary, bounded retries, quarantine queue.
- T3 Two-column and multi-page extraction errors. → layout-aware ordering + cross-page section stitching + golden-set regression tests.

**Data quality**
- D1 Near-duplicates → double-counting (real, observed).
- D2 Self-reported quantities presented as facts (real, pervasive).
- D3 Missing vs suppressed information (Hayes's Access route appears only in the letter).

**Privacy / fairness**
- F1 Candidate data sent to an LLM API without tenancy approval — **highest-severity project risk**; gate the whole pipeline on an approved endpoint (§20).
- F2 Proxy discrimination via writing style, verbosity, CV-polish (e.g. quantified-achievement culture), formatting sophistication — the corpus spans from dense-serif-formal to bold-claim-modern; a naive assessor would reward style.
- F3 Sensitive disclosures in free text (observed in `808_9158`) leaking into assessments.
- F4 "Confidence laundering": decimal confidence numbers that look scientific but are uncalibrated → we use categorical, rule-derived confidence instead.

**Assessment integrity**
- A1 Criteria drift: assessors mentally adding requirements ("no cover letter = not motivated") — forbidden; the framework must authorise every judgement.
- A2 Missing evidence ≠ negative evidence: the taxonomy and the UI enforce the distinction.

---

## 5. Recommended Architecture

### 5.1 Pipeline (revised from the brief's starting hypothesis)

The brief's 6 stages are kept, with three changes, each argued:

1. **Stage 0 added (Criteria & Config ingestion, before everything).** The job spec and assessment framework are themselves unstructured inputs needing parsing, ID assignment, and human sign-off. Without this stage, "criteria" exist only inside prompts — unauditable. *(Change: added.)*
2. **Packet splitting / page classification separated from document parsing.** The corpus proves the "document" is a container with junk pages, duplicates, and fragments. Ingestion therefore produces a **normalised packet model** (classified pages, merged duplicates) before any extraction. *(Change: split Stage 1 into 1a/1b.)*
3. **Verification & normalisation split from extraction.** Extraction is generative (LLM) and can hallucinate; verification is mostly deterministic and must be independently testable. Combining them hides extraction errors inside "verified" labels. *(Change: kept separate, as the brief hinted.)*

### 5.2 Stage list

```
Stage 0   Criteria ingestion & authoring        (hybrid: LLM parse + human sign-off)
Stage 1a  Packet intake & page classification   (deterministic + 1 small LLM classifier)
Stage 1b  OCR & provenance capture              (deterministic OCR; hybrid text correction off)
Stage 2   Extraction → Evidence items           (LLM, schema-constrained)
Stage 3   Verification & normalisation          (deterministic core + LLM ambiguity flagging)
Stage 4   Criteria mapping                      (hybrid: retrieval prefilter + LLM mapping)
Stage 5   Assessment per criterion              (LLM classification, evidence-cited)
Stage 6   Scoring                               (deterministic rubric engine)
Stage 7   Human review & overrides              (deterministic UI/report + audit)
Cross:    Redaction/sensitive-tagging (after 1b, gates 4-5); Audit log (all stages)
```

### 5.3 Non-negotiable invariants

- I1 Every Evidence item carries a verbatim quote + byte/character offsets + page + bounding box, resolvable to a rendered page image.
- I2 Every Assessment cites ≥0 Evidence IDs and exactly 1 Criterion ID; no criterion exists outside the Criteria Register.
- I3 Every Score is computed by `scoring-engine` from (assessment classification, rubric config); no LLM output can move a score directly.
- I4 Every artifact records `config_version`, `criteria_version`, `prompt_version`, `model_id`.
- I5 Sensitive-tagged content is excluded from mapping/assessment inputs by construction (query-level, not convention).

---

## 6. Architecture Diagram

```
                        ┌────────────────────────────────────────────┐
                        │  AUTHORISED INPUTS (human-owned, versioned)│
                        │  Job spec (PDF/DOCX) + Assessment framework│
                        └───────────────┬────────────────────────────┘
                                        ▼
              ┌───────────────────────── STAGE 0 ─────────────────────────┐
              │ Criteria Parser (LLM, schema-constrained)                 │
              │  → Criteria Register (criterion_id, weight, rubric refs)  │
              │  → HUMAN SIGN-OFF required → criteria_version frozen      │
              └─────────────────────────┬─────────────────────────────────┘
                                        │  criteria_version
CANDIDATE PACKET (PDF)                  ▼
      │
      ▼
┌───────────── STAGE 1a: PACKET INTAKE ─────────────┐
│ Page classifier: text layer? ink? divider? form?  │
│ → PacketModel{ pages[], docType[], duplicates[] } │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 1b: OCR & PROVENANCE ──────────┐
│ text-layer extraction | OCR (word boxes + conf)   │
│ → SourceText{ page, words[{text,bbox,conf}] }     │
│ → rendered page PNGs (review UI anchors)          │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── SENSITIVE-CONTENT TAGGING ───────────┐
│ deterministic PII patterns + LLM sensitive-topic  │
│ tagging → redacted/ tagged views for stages 4-5   │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 2: EXTRACTION ─────────────────┐
│ Section identification (hybrid)                   │
│ Evidence extraction per doc section (LLM+JSON)    │
│ → Evidence{ quote, offsets, category, claim_type }│
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 3: VERIFY & NORMALISE ─────────┐
│ deterministic: quote-match, dup merge, dates,     │
│ chronology, alias normalisation                   │
│ LLM-assisted: ambiguity/contradiction flags       │
│ → EvidenceState{VERIFIED_FROM_DOCUMENT|AMBIGUOUS| │
│    CONTRADICTORY|NOT_STATED|UNREADABLE}           │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 4: CRITERIA MAPPING ───────────┐
│ embedding prefilter → LLM mapping w/ mandatory    │
│ evidence citations → CriterionEvidence links      │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 5: ASSESSMENT ─────────────────┐
│ per criterion: LLM classifies evidence strength   │
│ {STRONG|EVIDENCE|PARTIAL|NONE_FOUND|CONFLICTING|  │
│  NOT_ASSESSABLE} + rationale citing evidence IDs  │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 6: SCORING (deterministic) ────┐
│ rubric engine: classification×rubric→band,        │
│ gate logic for essential criteria, weights,       │
│ coverage & uncertainty report                     │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────── STAGE 7: HUMAN REVIEW ───────────────┐
│ per-criterion report w/ drill-down to page image  │
│ + highlight boxes; overrides recorded w/ rationale│
└───────────────────────────────────────────────────┘
                ▼
        AUDIT LOG (append-only, every stage)
```

---

## 7. Pipeline Stage Definitions

Each stage: **Inputs / Processing / Outputs / Validation / Failure modes / Responsibility**.

### Stage 0 — Criteria ingestion & authoring
- **Inputs:** Job specification document; assessment framework document (DOCX/PDF/MD).
- **Processing:** LLM parses into draft `JobCriterion[]` (id, description, category, essential/desirable, weighting, evidence expectation, scoring rule). Deterministic ID assignment (`CR-001`…). Human reviewer edits/approves in a criteria-review UI (can be a structured YAML file + PR review for v1). Frozen as `criteria_version` (semver).
- **Outputs:** `CriteriaRegister` (JSON/YAML, versioned).
- **Validation:** schema validation; weighting sum check (if absolute); uniqueness of IDs; every criterion has evidence expectation; rubric referenced exists.
- **Failure modes:** missing weighting scheme; ambiguous criteria ("good communicator") → flagged `NEEDS_CLARIFICATION`, excluded until human resolves.
- **Responsibility:** **Hybrid** — LLM for parsing, deterministic for IDs/validation, **human for authorisation**. The LLM may never add criteria not derivable from the supplied documents.

### Stage 1a — Packet intake & page classification
- **Inputs:** candidate PDF (or DOCX/other).
- **Processing (deterministic):** render pages (PyMuPDF); extract text layer; compute ink ratio; hash pages; detect near-duplicates (perceptual hash + OCR-text similarity); rule-based classification (text-layer form detection; divider banners; blank pages; "No data available").
- **LLM use:** one small classification call per *unresolved* page (multi-modal: page image) with output `{page_type: CV|COVER_LETTER|FORM|PORTFOLIO|DIVIDER|BLANK|UNKNOWN|OTHER, contains_substantive_content: bool, confidence_band}`.
- **Outputs:** `PacketModel` with `Document[]` (each a grouped page-range with type), duplicate groups, rendering PNGs.
- **Validation:** every page classified or explicitly `UNKNOWN`; duplicate groups must not span different types; packet must contain ≥1 `CV`-type doc else `INCOMPLETE_PACKET` warning (not an assessment outcome).
- **Failure modes:** encrypted PDF; unreadable PDF; unknown file type → pipeline failure with human task; never a score.
- **Responsibility:** mostly **deterministic**; LLM only for genuinely ambiguous pages (in this corpus: the divider/form/blank pages resolve deterministically; the Holme two-column page and the Hayes duplicate need no LLM — dedup handles them).

### Stage 1b — OCR & provenance capture
- **Inputs:** rendered page images + text layers.
- **Processing:** for text-layer pages, extract text + coordinates directly. For image pages: OCR with **word-level bounding boxes and confidence**; preserve reading order hints (column detection via x-histogram clustering). Store per-page `SourceText` with char-offset↔word-box mapping so any quote can be highlighted on the page image.
- **Outputs:** `SourceText[]` (one per document page), page PNGs.
- **Validation:** word-confidence distribution per page; pages with mean OCR confidence below threshold → flagged `LOW_QUALITY_OCR` (downstream shows `NOT_ASSESSABLE` where relevant). Deterministic spot-checks: email/phone/URL patterns must OCR cleanly (regex-verifiable tokens).
- **Failure modes:** OCR engine failure (retry once, then `OCR_FAILED` manual-review); rotated pages (auto-orient); empty result despite ink present (manual review).
- **Responsibility:** **deterministic**. **No LLM "clean-up" of OCR text**: correcting text with a model would falsify provenance. Verbatim quotes must match OCR output byte-for-byte (verification regex/similarity check), so any correction happens at the *normalised value* level, with the raw quote retained.

### Sensitive-content tagging (cross-cutting gate)
- **Processing:** deterministic PII detectors (emails, phones, addresses, postcodes, names via the ATS form) + one LLM pass tagging sensitive topics (nationality/immigration, family, health, religion, age signals, photos, assessment history).
- **Outputs:** `SensitiveSpan[]` linked to evidence; a **redacted view** of every SourceText used by Stages 4–5.
- **Responsibility:** hybrid; deterministic where possible. Fail-closed: if tagging fails, Stages 4–5 run on fully redacted text (degraded, flagged) rather than untagged text.

### Stage 2 — Extraction
- **Inputs:** `PacketModel` + `SourceText` (sections identified first).
- **Processing:** (a) **Section identification**: deterministic heading heuristics (font-size clusters from OCR, ALL-CAPS, rule lines) propose sections; LLM validates/labels sections per page-range (one call per document, output `Section[]` with type enum: PROFILE, EXPERIENCE, EDUCATION, SKILLS, PROJECTS, ACHIEVEMENTS, EXTRACURRICULAR, OTHER). Cross-page stitching merges split sections. (b) **Evidence extraction**: one LLM call per section with the section text (raw OCR quotes) → `EvidenceItem[]`, each with verbatim `quote` (must substring-match SourceText), location, `category` (enum), `claim_type` (see §8), and `stated_date_range` where present.
- **Outputs:** `EvidenceItem[]` (unverified).
- **Validation:** schema validation; quote substring check (allowing OCR whitespace variance); category enum; no empty quotes; per-item extraction method tag; ambiguity status initialised `AMBIGUOUS` until Stage 3 confirms.
- **Failure modes:** malformed JSON (retry ≤2 with error message, then quarantine); section too long (recursive chunking with overlap, dedup by quote); contradictory facts within a section (extract both, mark `CONTRADICTORY_CANDIDATE`).
- **Responsibility:** **LLM** (semantic), with deterministic pre/post-processing. The extraction prompt is *forbidden* from assessing quality or fit — it only records what is stated (enforced by output schema having no evaluative fields).

### Stage 3 — Verification & normalisation
- **Inputs:** `EvidenceItem[]`, `PacketModel`, `SourceText`.
- **Processing (deterministic):** quote re-verification against SourceText; duplicate/near-duplicate evidence merge (across the duplicate CV/letter copies) keeping all locations; date parsing to intervals with precision; employment chronology assembly (overlaps, gaps, future-dated items); skill-alias normalisation against the versioned alias registry; unsupported-extraction detection (evidence without location).
- **Processing (LLM-assisted, flagged):** contradiction & ambiguity detection between items (e.g., different grad years in CV vs letter); attributing evidence to the correct role when context is unclear. LLM output can only *flag*, never *resolve* — resolution sets state to `AMBIGUOUS` pending human review, or to `VERIFIED_FROM_DOCUMENT` only via deterministic rules.
- **Outputs:** verified `Evidence[]` with `EvidenceState`, normalised values, `VerificationCheck[]` results.
- **Validation:** every evidence has a state; every normalised value has a method + raw original; no state `VERIFIED_FROM_DOCUMENT` without deterministic check having passed.
- **Failure modes:** alias conflict (two different skills normalise to same id) → registry fix + version bump; unparseable date → keep raw + `DATE_UNPARSED`.
- **Responsibility:** **deterministic core**; LLM only as flag-raiser.

### Stage 4 — Criteria mapping
- **Inputs:** verified `Evidence[]` (sensitive-tagged content excluded), `CriteriaRegister`.
- **Processing:** embedding retrieval shortlists evidence per criterion (cheap, deterministic-ish); LLM mapping call per criterion: given the criterion (description + evidence expectation) and candidate evidence shortlist, return links with `{criterion_id, evidence_ids[], mapping_rationale, mapping_type: DIRECT|RELATED|UNCLEAR}`. Every `evidence_id` must exist and belong to the candidate; hallucinated IDs are a validation failure.
- **Outputs:** `CriterionEvidence[]` links.
- **Validation:** referential integrity; criterion must exist in the register; evidence must be in this candidate's packet; sensitive-tagged evidence rejected at query level.
- **Failure modes:** criterion with zero mapped evidence → that is a valid outcome (`NO_EVIDENCE_FOUND` at Stage 5); mapping call failure → retry, then `MAPPING_INCOMPLETE` flag (assessment proceeds with explicit incompleteness, surfaced in review UI).
- **Responsibility:** **hybrid**.

### Stage 5 — Assessment
- **Inputs:** `CriterionEvidence[]`, `Evidence[]`, criterion definitions.
- **Processing:** per criterion, one LLM classification call: output `{criterion_id, assessment_class, rationale, cited_evidence_ids[], uncertainty_notes[]}`. Classes: `STRONG_EVIDENCE | EVIDENCE | PARTIAL_EVIDENCE | NO_EVIDENCE_FOUND | CONFLICTING_EVIDENCE | NOT_ASSESSABLE`. Prompt constraints: may cite only supplied evidence IDs; must use `NO_EVIDENCE_FOUND` (never "not met") when nothing maps; must use `CONFLICTING_EVIDENCE` when evidence disagrees; must downgrade to `PARTIAL` when evidence is single-source self-declaration.
- **Outputs:** `Assessment[]`.
- **Validation:** cited IDs exist; rationale non-empty and quote-grounded (rationale must reference at least one quote fragment — deterministic check); class enum; one assessment per criterion per candidate.
- **Failure modes:** missing assessment for a criterion → `NOT_ASSESSABLE` + warning; API failure → retry/backoff, then staged failure (candidate marked `ASSESSMENT_INCOMPLETE`, excluded from scoring, human task).
- **Responsibility:** **LLM**, narrowly constrained; reproducibility supported by fixed model version, temperature 0, cached runs.

### Stage 6 — Scoring (deterministic engine)
- See §13. **Responsibility: 100% deterministic code.**

### Stage 7 — Human review
- See §21. **Responsibility: deterministic reporting + human judgement.**

---

## 8. Canonical Data Model

Entities and the traceability chain. Every entity carries `id`, `created_at`, `config_version`.

```
CandidatePacket 1─* Document 1─* Page 1─1 SourceText 1─* WordBox
                         │              │
                         │              └─* SensitiveSpan
                         └─* Section 1─* EvidenceItem ──* EvidenceLocation──> Page(+bbox)
                                          │
                        (merge/verify)    ▼
                                       Evidence  (normalised, stateful)
                                          │
CriteriaRegister 1─* JobCriterion 1─* CriterionEvidence *─1 Evidence
                                        │
                                        ▼
                                    Assessment 1─0..1 CriterionScore
                                        │
                                        ▼
                              CandidateResult (aggregate, coverage, gates)
                                        │
                                        ▼
                              ReviewDecision (human, override, rationale)
Every stage transition emits ──> AuditEvent (append-only)
```

Key entities (fields abbreviated; full JSON in §9):

- **CandidatePacket**: `packet_id` (ATS numeric id), `files[]`, `intake_status`.
- **Document**: type (`CV|COVER_LETTER|FORM|PORTFOLIO|OTHER`), page range, `duplicate_of_document_id?`.
- **Page**: index, image path, ocr engine + version, mean confidence.
- **SourceText / WordBox**: raw OCR words with bbox + confidence; char-offset index.
- **Section**: doc-scoped, type enum, page spans, heading text.
- **EvidenceItem → Evidence**: `claim_type` ∈ {`STATED_FACT`, `STATED_CLAIM` (self-assessed proficiency, opinion), `STATED_METRIC` (quantified achievement), `NORMALISED_VALUE`, `INFERRED` (discouraged; always flagged)}. Evidence carries ≥1 location, `state`, `normalised` payload (skill ids, org, dates, etc.).
- **JobCriterion**: `criterion_id`, `description`, `category`, `essential: bool`, `weighting` (nullable — desirable criteria may be unweighted), `evidence_expectation` (what counts as evidence), `scoring_rule_ref`, `version`.
- **CriterionEvidence**: many-to-many link + `mapping_type` + `mapping_rationale`.
- **Assessment**: class, rationale, uncertainty, citations.
- **CriterionScore**: band, numeric (nullable), contributing inputs, rubric version.
- **ReviewDecision**: reviewer, action (`CONFIRM|OVERRIDE|FLAG`), previous→new value, rationale, timestamp.
- **AuditEvent**: actor (`stage`/`human`), action, payload hash, versions, timestamp.

**"No evidence found" vs negative evidence:** the Evidence model has no "absent" rows; absence is represented *only* in Assessment as `NO_EVIDENCE_FOUND`, and the UI wording is fixed ("No evidence located in submitted documents" — never "lacks X").

---

## 9. Example JSON Schemas

### 9.1 Evidence (verified)

```json
{
  "evidence_id": "EV-8087949-000123",
  "packet_id": "808_7949",
  "claim_type": "STATED_METRIC",
  "category": "TECHNICAL_EXPERIENCE",
  "raw_quote": "personally improving the aerodynamic efficiency by 18% from the original baseline",
  "locations": [
    {"document_id": "DOC-8087949-CV", "page": 2,
     "char_start": 1410, "char_end": 1491,
     "bbox": [96, 445, 512, 462]}
  ],
  "state": "VERIFIED_FROM_DOCUMENT",
  "normalised": {
    "skill_ids": ["SKILL-CFD", "SKILL-ANSYS-FLUENT"],
    "org": "Team Bath Racing Electric",
    "date_range": {"earliest": "2024-11", "latest": "2026-07", "precision": "month"},
    "metric": {"value": 18, "unit": "percent", "claimed_by": "candidate"}
  },
  "extraction": {"method": "llm-extract-v3", "prompt_version": "3.1.0", "model_id": "…"},
  "verification": {"quote_match": true, "checks": ["QUOTE_MATCH", "DATE_PARSE", "ALIAS_NORMALISE"]},
  "sensitive_tags": [],
  "ambiguity": {"status": "NONE", "notes": []}
}
```

### 9.2 LLM extraction output contract (Stage 2)

```json
{
  "type": "object",
  "required": ["evidence_items"],
  "additionalProperties": false,
  "properties": {
    "evidence_items": {
      "type": "array",
      "maxItems": 40,
      "items": {
        "type": "object",
        "required": ["raw_quote", "category", "claim_type", "approx_location"],
        "additionalProperties": false,
        "properties": {
          "raw_quote":      {"type": "string", "minLength": 15, "maxLength": 600},
          "approx_location": {"type": "string", "description": "nearby heading or section context, verbatim if possible"},
          "category": {"enum": ["QUALIFICATION","EMPLOYMENT","ROLE_TITLE","RESPONSIBILITY","TECHNICAL_SKILL",
                                "TOOL_SOFTWARE","PROJECT","ACHIEVEMENT","DOMAIN_EXPERIENCE","LEADERSHIP",
                                "DATE_FACT","OTHER"]},
          "claim_type": {"enum": ["STATED_FACT","STATED_CLAIM","STATED_METRIC"]},
          "stated_date_range": {"type": ["string", "null"]},
          "related_role_or_project": {"type": ["string", "null"]},
          "ambiguity_note": {"type": ["string", "null"]}
        }
      }
    },
    "section_split_or_truncation_suspected": {"type": "boolean"}
  }
}
```

Validation: quotes are substring-matched against SourceText (whitespace-tolerant); failure → bounded retry with the mismatching quote returned to the model → quarantine if still failing.

### 9.3 Assessment output contract (Stage 5)

```json
{
  "type": "object",
  "required": ["criterion_id", "assessment_class", "cited_evidence_ids", "rationale"],
  "additionalProperties": false,
  "properties": {
    "criterion_id": {"type": "string", "pattern": "^CR-[0-9]{3}$"},
    "assessment_class": {"enum": ["STRONG_EVIDENCE","EVIDENCE","PARTIAL_EVIDENCE",
                                   "NO_EVIDENCE_FOUND","CONFLICTING_EVIDENCE","NOT_ASSESSABLE"]},
    "cited_evidence_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 15},
    "rationale": {"type": "string", "minLength": 50, "maxLength": 1200},
    "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
    "contradicting_evidence_ids": {"type": "array", "items": {"type": "string"}}
  }
}
```

---

## 10. Job Criteria Model

```yaml
criteria_version: 1.0.0
 authorised_by: "<name/role + date>"        # mandatory provenance of authorisation
 weighting_scheme: "weighted_mean_bands"     # or "unweighted_gates_only"
 criteria:
   - criterion_id: CR-001
     description: "Proficiency in CAD for aerodynamic surface modelling (e.g. SolidWorks, CATIA, NX, Fusion 360, Onshape)"
     category: TECHNICAL_SKILL
     essential: true
     weighting: 3                            # relative weight; scheme defined at register level
     evidence_expectation: >
       Named CAD tool(s) applied to aerodynamic or vehicle geometry work.
       Tool listing alone is PARTIAL; application in a project/experience context is EVIDENCE;
       repeated application across contexts with outcomes is STRONG.
     scoring_rule_ref: rubric/default
     notes: "Alias registry resolves tool synonyms; self-declared proficiency levels are claims."
```

Notes:
- The `evidence_expectation` field is the crucial anti-drift device: it pre-commits what evidence counts, so Stage 5 classification is anchored to the framework, not the model's taste.
- **Job-spec parsing is its own pre-processing pipeline** (Stage 0): the alternative — embedding the raw job spec text into assessment prompts — was rejected because it lets the model improvise requirements at assessment time and destroys versioning.

---

## 11. Evidence Mapping Method

1. Deterministic prefilter: for skill/tool criteria, inverted index over normalised `skill_ids` gives exact candidates — no LLM needed for the obvious cases (e.g. CR "CAD proficiency" ↔ evidence with `skill_ids:[SKILL-SOLIDWORKS]`).
2. Embedding retrieval (off-the-shelf sentence embeddings, local model) shortlists top-k evidence per criterion for semantic criteria (e.g. "leadership experience").
3. LLM mapping confirms/extends the shortlist **with mandatory citations and a mapping rationale**; it may retrieve evidence the embeddings missed only from the full (redacted) evidence list of that candidate.
4. Human spot-check sampling in validation (§17): mapping precision is audited per criterion.

OPEN QUESTION: whether mapping should be *conservative* (only DIRECT mappings feed scoring) by default — provisional recommendation: yes for essential criteria; RELATED may feed `PARTIAL_EVIDENCE` maximum.

---

## 12. Assessment Method

- One assessment record per (candidate, criterion), citing evidence IDs, classified into:

| Class | Meaning (anchored in evidence_expectation) |
|---|---|
| `STRONG_EVIDENCE` | Multiple independent in-packet items, or one item with specific detail + outcomes, matching the expectation |
| `EVIDENCE` | Clear stated evidence matching the expectation |
| `PARTIAL_EVIDENCE` | Related but weaker (single mention, listing without application, self-rating only) |
| `NO_EVIDENCE_FOUND` | Mapping produced nothing — **does not imply the candidate lacks it** |
| `CONFLICTING_EVIDENCE` | Evidence items disagree (e.g. different dates/claims across CV and letter) |
| `NOT_ASSESSABLE` | OCR/quality/processing failure prevented evaluation |

- Reproducibility: fixed model version pinned per `config_version`, temperature 0, structured output, and assessment runs are idempotent — re-running the same config on the same packet must yield identical output (cached; non-identical output is a regression-test failure).
- The prompt may not see: candidate name/photo-free identity fields, sensitive spans, other candidates, or any aggregate/ranking information. Sequential independence: each criterion assessed in isolation to prevent halo effects.

---

## 13. Scoring Method

**Recommendation: deterministic rubric engine; LLM never computes or modifies scores.**

```
Criterion
   → Assessment class (from Stage 5)
   → rubric map (from config): class → band (e.g. STRONG=4, EVIDENCE=3, PARTIAL=1,
      NO_EVIDENCE_FOUND=null, CONFLICTING=null, NOT_ASSESSABLE=null)
   → essential-criteria gate: if essential and band is null → GATE:INSUFFICIENT_EVIDENCE
      (result flagged, not zeroed — zero would assert failure)
   → weighting applied only over criteria with a numeric band
   → weighted mean + coverage % (share of weightable criteria that got a band)
```

Design decisions:
- `NO_EVIDENCE_FOUND` and `CONFLICTING_EVIDENCE` yield **null, not 0**. A 0 asserts the criterion is unmet; null asserts "we could not determine" — the difference the brief demands. Coverage % makes the gap visible; a result with coverage below a configured floor (e.g. 60%) is reported as `LOW_COVERAGE` and goes to human review before any comparative use.
- Uncertainty is **not** inside the number: bands are discrete and published in the rubric config; every score ships with its band, its evidence count, and open uncertainty notes.
- Essential criteria are gated (pass/pending), desirable criteria contribute weighted bands.
- If the framework supplies no weightings: output is per-criterion bands only, plus an unweighted aggregate clearly labelled as such. **No invented weights.**
- Output example:

```json
{
  "packet_id": "808_7949",
  "criteria_version": "1.0.0",
  "scoring_config_version": "1.0.0",
  "gates": {"CR-001": {"status": "PASS", "band": 4},
            "CR-004": {"status": "INSUFFICIENT_EVIDENCE"}},
  "criterion_bands": {"CR-001": 4, "CR-002": 3, "CR-005": null, "…": null},
  "weighted_mean": 3.4,
  "coverage": 0.82,
  "coverage_flags": ["LOW_COVERAGE_THRESHOLD_NOT_TRIGGERED"],
  "provisional": true,
  "excluded_from_scoring": ["CR-005:CONFLICTING_EVIDENCE", "CR-007:NO_EVIDENCE_FOUND"]
}
```

---

## 14. Confidence and Uncertainty Model

**Recommendation: categorical, rule-derived confidence — no raw model probabilities, no invented decimals.**

```
Evidence confidence:  HIGH | MEDIUM | LOW
  derived deterministically from:
   - OCR word confidence along the quote span (band thresholds)
   - quote-match verification result
   - corroboration count (same fact stated in CV and letter)
   - validation state (checks passed)

Assessment confidence: HIGH | MEDIUM | LOW
  derived from:
   - minimum evidence confidence among citations
   - number of independent cited items
   - presence of ambiguity/contradiction flags
   - mapping completeness for the criterion
```

Strengths: explainable to reviewers and candidates' representatives; stable across model versions; auditable rules. Weaknesses: coarser than a calibrated probability; thresholds need tuning against the golden set (§24); cannot express graded uncertainty within a band (mitigated by uncertainty notes). Model logits were rejected because LLM verbalised/logit confidence is poorly calibrated for extraction tasks and would imply a precision we do not have.

---

## 15. LLM vs Deterministic Responsibility Matrix

| Capability | Approach | Rationale |
|---|---|---|
| ATS form field extraction | **Deterministic** | Label/value pairs in text layer; regex/rules suffice (observed in corpus) |
| Page classification | **Deterministic first**, LLM fallback | Ink/divider/blank rules resolved 100% of corpus pages; LLM only for the residue |
| Duplicate detection | **Deterministic** | Hashing + text similarity; observed duplicates caught |
| OCR | **Deterministic** (OCR engine) | Provenance requires non-generative text capture |
| OCR correction | **Neither** (do not correct) | Correction falsifies provenance; normalise at value level instead |
| Column/order detection | **Deterministic** (layout algorithms) | Geometric problem |
| Section identification | **Hybrid** | Headings are layout signals; labelling novel sections is semantic |
| Evidence extraction | **LLM** | Core semantic task; schema-constrained |
| Date parsing/arithmetics | **Deterministic** (parser library) | Rules are reliable; LLM dates are a known failure source |
| Skill/terminology normalisation | **Deterministic registry** + LLM suggestions | Deterministic where the registry covers; LLM proposes new aliases, human curates |
| Duplicate-evidence merge | **Deterministic** | Similarity thresholds |
| Contradiction/ambiguity flagging | **LLM (flags only)** | Semantic; but cannot auto-resolve |
| Criteria parsing (Stage 0) | **Hybrid** | LLM parse + human authorise |
| Criteria→evidence mapping | **Hybrid** | Retrieval + LLM citation-checked |
| Assessment classification | **LLM** | Judgement task, tightly constrained |
| Scoring | **Deterministic** | Rules; auditability; no model drift on numbers |
| Weighting application | **Deterministic** | Config-supplied only |
| Sensitive-content tagging | **Hybrid** | Regex PII + LLM topic tags; fail-closed |
| Audit logging | **Deterministic** | Append-only events |
| Review overrides | **Human** | Recorded, versioned |

General principle honoured: the LLM is used exactly where reading-between-the-lines is required, and each such use is citation-checked by deterministic code afterwards.

---

## 16. Prompt Architecture

Separate prompts per responsibility (no monolithic extract-and-judge prompt). Interfaces only; prompt texts authored at implementation time.

| Prompt | Purpose | Permitted inputs | Required structured output | Key restrictions / safeguards |
|---|---|---|---|---|
| P0 `criteria-parse` | Draft criteria from authorised docs | Job spec + framework text only | `CriteriaDraft{criteria[]}` | Must not add criteria absent from source; ambiguity → `NEEDS_CLARIFICATION` |
| P1 `page-classify` | Classify unresolved pages | Page image | `{page_type, contains_substantive_content}` | No content extraction on this pass |
| P2 `section-identify` | Label sections for a document | OCR text w/ layout markers | `Section[]` | Types from enum only; must preserve page spans |
| P3 `evidence-extract` | Extract evidence items from one section | Section text (raw OCR) | `EvidenceItem[]` (schema §9.2) | **No evaluative fields in schema**; verbatim quotes only; must set `section_split_or_truncation_suspected` when applicable |
| P4 `contradiction-flag` | Flag inconsistencies across evidence | Redacted evidence set | `Flag[]` | Flags only; no resolutions |
| P5 `criteria-map` | Map evidence to one criterion | Criterion + redacted evidence shortlist | `CriterionEvidence[]` w/ citations | Citations must reference supplied IDs |
| P6 `assess-criterion` | Classify evidence strength for one criterion | Criterion + mapped evidence + expectation | schema §9.3 | No comparisons to other candidates; `NO_EVIDENCE_FOUND` ≠ failure; temperature 0 |
| P7 `sensitive-tag` | Tag sensitive spans | Page text | `SensitiveSpan[]` | Fail-closed behaviour downstream |

Cross-prompt invariants: every prompt receives a system preamble stating the evidence-first rules; every output is schema-validated; every prompt+model version is pinned in `config_version` and recorded per artifact.

---

## 17. Validation Strategy

Boundary checks (all automated unless noted):

| Boundary | Automated checks |
|---|---|
| Document → parsing | Page count sane, render success, text-layer/OCR presence where ink exists, duplicate map built |
| Parsed → extraction | Schema validation; quote substring-match; category/claim enums; locations resolvable |
| Evidence → source | Quote re-verification; bbox on-page; date parse rate monitored |
| Normalised evidence | Every normalised value has method + raw original; alias ids exist in registry |
| Assessment | Citation referential integrity; rationale quote-grounded; one assessment per criterion |
| Score | Rubric version exists; bands valid; weights from config; coverage computed; gate logic unit-tested |
| **Human sampling** | Per campaign: random sample (e.g. 10 packets / 100 evidence items / all assessments for 3 candidates) reviewed against source; measured: extraction precision, mapping precision, assessment-class agreement with reviewer |

Sample-based human evaluation is mandatory for extraction and assessment — automation cannot certify semantic fidelity.

---

## 18. Error Handling Strategy

| Failure | Handling |
|---|---|
| Unreadable/encrypted/unsupported file | **Pipeline failure** → human task; candidate not assessed |
| OCR failure on a page | Retry once → else page marked `UNREADABLE`; dependent assessments `NOT_ASSESSABLE` |
| Low OCR confidence (page/word) | Warning; evidence confidence downgraded; may force `NOT_ASSESSABLE` |
| Malformed LLM output | Schema error fed back, retry ≤2 → quarantine record + manual review; **never** defaults to an assessment |
| LLM/API outage | Exponential backoff, staged resume; batch marked `ASSESSMENT_INCOMPLETE` |
| Missing job criteria / criteria validation error | **Stage 0 blocks** the campaign; no assessment can start |
| Scoring config errors (missing rubric, bad weights) | Engine refuses to emit scores; error surfaces to operator |
| Contradictory evidence | Assessment `CONFLICTING_EVIDENCE`; scoring excludes; reviewer sees both items |
| Duplicate document | Merged with all locations retained; warning logged |
| Near-empty packet (e.g. `808_5422`'s missing letter) | Packet metadata `INCOMPLETE_PACKET`; **not** an assessment outcome |

---

## 19. Audit and Traceability Design

- **Append-only `AuditEvent` log** (JSONL per campaign + DB table), each event: `{event_id, ts, stage, actor, action, artifact_ids, input_hash, output_hash, config_version, criteria_version, prompt_versions, model_id, warnings[]}`.
- Every artifact (evidence, assessment, score, decision) stores its producing `config_version` and parent artifact ids — the full chain Score→Assessment→CriterionEvidence→Evidence→SourceText→Page→PDF is queryable via ids alone.
- Config store (versioned files in repo + frozen copies per campaign): criteria register, scoring rubric, prompt texts, model ids, thresholds.
- Reconstruction test (acceptance criterion): given a campaign id, the system can re-render the complete reasoning trail for any candidate offline, from the audit log alone.
- Human overrides are first-class `ReviewDecision` artifacts with before/after and rationale; the original machine assessment is never mutated.

---

## 20. Privacy, Security and Responsible AI Controls

- **Approved LLM endpoint only** (OPEN QUESTION — gating). Provisional recommendation: tenancy-approved enterprise endpoint with no-training/zero-retention contract (e.g. Azure OpenAI in the organisation's tenant with Private Link), or local model for development. No candidate data to consumer endpoints, ever.
- **Data minimisation by construction**: primary key is the ATS numeric id; names/contacts live in the SourceText (needed for traceability) but are excluded from all prompts except P1/P2/P7 which need the page content, and are redacted there where feasible.
- **Sensitive span redaction** (fail-closed) before mapping/assessment; observed corpus items handled: nationality & family origin (`808_9158`), named recruiters & assessment history (`808_7949`), addresses/phones (all).
- **No proxy inference**: no criteria derived from historical hiring data; no stylistic scoring; hobbies/interests only enter if an authorised criterion explicitly covers relevant interests, and then identically for all candidates.
- **Storage**: encrypted at rest; access-role separation (operators vs reviewers); per-campaign workspaces with retention timer (OPEN QUESTION: retention period — provisional: delete documents + derived artifacts N months after campaign close, retaining anonymised aggregates + audit log with hashes).
- **Logging hygiene**: structured logs with PII scrubbing; prompts and completions stored only in the audit store, never in app logs; no candidate data in telemetry.
- **Dev/test data**: synthetic + redacted fixtures only; a documented rule forbids copying real packets into dev (enforced by fixture naming + code-review checklist). The supplied examples are treated as sensitive for this purpose.
- **Human oversight**: autonomous rejection forbidden; comparative ranking suppressed until human review completes; system outputs labelled "provisional, evidence-based, subject to human review".

---

## 21. Human Review Workflow

Per candidate, the reviewer sees one screen per criterion (and an aggregate view):

```
CR-001  CAD proficiency for aero surface modelling        [ESSENTIAL] weight 3
Assessment: STRONG_EVIDENCE          Confidence: HIGH      Score band: 4/4
Rationale: "Named SolidWorks and CATIA applied to … (EV-…-000123, EV-…-000131)"
Evidence (3): ▸ each item: quote, source doc/page, [View page] → opens page PNG,
              bbox highlighted; corroborated across CV + letter
Uncertainty: none flagged
Review action:  [ Confirm ]  [ Override class → (select) ]  [ Flag for discussion ]
Override requires: rationale (min length) + reviewer identity → ReviewDecision artifact
```

- Overrides never edit evidence — reviewers may suppress an evidence item (recorded) and re-run deterministic scoring, or override the class/rubric band with rationale.
- Reviewer queue supports triage order but the system must not auto-order candidates by score (no unexplained ranking); sorting is reviewer-initiated and labelled.

---

## 22. Recommended Technology Stack

| Concern | Recommendation | Alternatives considered | Trade-offs / rationale |
|---|---|---|---|
| Language | **Python 3.12+** | C#/.NET, Node | Team tooling (pymupdf/pydantic/pytest ecosystem), VS Code-first |
| PDF/render | **PyMuPDF (fitz)** | pdfplumber, pypdfium2 | Fast rendering + text layer + word boxes in one lib; AGPL licence — flag for commercial review (fallback: pypdfium2, Apache-2.0) |
| OCR | **Tesseract via pytesseract** for v1; evaluate **PaddleOCR** in a spike (better on styled/coloured text like the Holme sidebar) | Cloud OCR (Azure Doc Intelligence / Google Doc AI) | Local = privacy + cost; Tesseract simple, weaker on colour/small-caps; PaddleOCR stronger but heavier; cloud OCR most accurate but sends candidate data off-premise — only with approval. **Spike decides; golden-set OCR accuracy is the metric** |
| Schema/validation | **pydantic v2** | jsonschema | Typed models shared by code + validation; fast |
| LLM integration | **Thin client** (official SDK / HTTP) + structured outputs; **no LangChain** | LangChain/LlamaIndex, Instructor | Pipeline is simple and inspectable; frameworks add opacity and churn for little gain here. Instructor optional later for retries |
| LLM provider | **Tenancy-approved enterprise endpoint**; local (Ollama/vLLM w/ small instruct model) for dev w/o candidate data | Consumer APIs | Privacy gating (§20) |
| Embeddings (retrieval) | **Local sentence-transformers model** | API embeddings | Data stays local; retrieval is a prefilter, not a judge |
| Persistence | **SQLite (dev/campaign) → PostgreSQL (if multi-user/multi-campaign)** | Full Postgres from day 1 | Avoid infra until needed; schema kept portable |
| Page store | Filesystem (PNG + JSON sidecars), content-addressed paths | Object storage | Campaign scale is small; object storage unnecessary now |
| CLI/orchestration | **Typer** CLI + **batch runner** with resume; **no Airflow/Prefect** | Workflow engines | Batch jobs are linear per packet; a workflow engine is complexity without payoff at this scale |
| Logging | **structlog**, JSON logs, PII-scrubbed processors | print/logging | Audit-adjacent hygiene |
| Testing | **pytest** + golden-set harness + coverage | — | Standard, VS Code-native |
| Config | **YAML + pydantic settings**, frozen per campaign | DB config | Versionable in git, diffable in review |
| Review UI (v1) | Generated **HTML report** (self-contained, links to page PNGs) served from repo tools; interactive UI later | React app, Streamlit | Keep increment small; the report is the deliverable reviewers need first |
| VS Code | devcontainer (Python + Tesseract), recommended extensions, tasks for test/lint, launch configs for CLI debugging | — | Reproducible onboarding |

---

## 23. VS Code Repository Structure

```
test-1/
├─ docs/                        # this plan, ADRs (decision log entries live here too)
├─ src/cvreview/
│  ├─ config/                   # settings loading, config_version freezing
│  ├─ criteria/                 # Stage 0: parsing, register model, validation
│  ├─ ingestion/                # 1a page classify, 1b OCR, provenance, dedup
│  ├─ redaction/                # sensitive span tagging, redacted views
│  ├─ extraction/               # Stage 2: sections, evidence extraction
│  ├─ verification/             # Stage 3: checks, normalisation, chronology
│  ├─ mapping/                  # Stage 4: retrieval + mapping
│  ├─ assessment/               # Stage 5: classification
│  ├─ scoring/                  # Stage 6: deterministic rubric engine
│  ├─ review/                   # Stage 7: report generation
│  ├─ audit/                    # event log, reconstruction tooling
│  ├─ llm/                      # thin client, structured-output helpers, retries
│  └─ schemas/                  # pydantic models (single source of truth)
├─ prompts/                     # P0..P7 prompt sources, versioned, CHANGELOG per prompt
├─ config/                      # criteria/*.yaml, rubrics/*.yaml, thresholds, models
├─ data/
│  ├─ fixtures/                 # synthetic + redacted test packets ONLY (no real data)
│  └─ goldens/                  # expected evidence/assessments for golden set
├─ tests/
│  ├─ unit/  ├─ integration/  ├─ regression/  ├─ fairness/
├─ tools/                       # CLI entry points, report builder, audit reconstructor
├─ .devcontainer/  ├─ .vscode/  ├─ pyproject.toml  └─ README.md
```

Deliberate deviations from the brief's sketch: `normalisation` folded into `verification` (they share the check harness); `schemas` as code (pydantic) rather than a data folder; `prompts/` at top level because prompt versioning is an audit concern, not an implementation detail; `redaction/` added (not in sketch) because fairness gating needs a first-class home.

---

## 24. Testing and Evaluation Strategy

- **Unit (deterministic components):** date parsing (corpus cases: "Aug 2026 - Present", "2024-Present", "October 2022 – Present", mixed precision), alias normalisation (Star-CCM+ variants, CATIA variants), duplicate merge, quote verifier (incl. OCR whitespace tolerance), rubric engine (bands, gates, weights, coverage, config-error refusals), redaction fail-closed.
- **Golden-set extraction testing:** for each of the 7 supplied packets, hand-curate expected evidence (target: every criterion-relevant fact with location); metric = evidence recall/precision per document; regression gate on changes.
- **Regression:** frozen fixtures + pinned model versions; CI runs the full pipeline on goldens and diffs outputs (evidence sets, assessment classes, scores). Any diff requires explicit review → golden update commit referencing the change. Prompt/model changes always ship with regenerated goldens + rationale.
- **Edge-case fixtures (synthetic, from corpus-observed patterns):** two-column sidebar CV; page-break-split role; orphaned date line; truncated line; duplicate CV/letter; "No data available" page; skills listed without experience; overlapping employment; future-dated roles; very short CV (single page, no metrics); very long CV (6+ pages); missing cover letter; scanned low-quality page.
- **Fairness testing:** (a) perturbation tests — re-run extraction/assessment with perturbed surfaces: changed fonts/layout, reordered sections, gendered/neutral phrasing swaps, added hobbies, added nationality sentence (must not change any assessment class — automated assertion); (b) sensitive-span leakage test — assert no sensitive-tagged evidence appears in any CriterionEvidence link; (c) style controls — a template-controlled synthetic pair (same content, "polished" vs "plain" formatting) must score identically; (d) missing-evidence sanity — appending irrelevant text must never move `NO_EVIDENCE_FOUND` classes.
- **OCR quality gate:** golden pages OCR'd at each engine/version bump; accuracy regression blocks adoption.

---

## 25. Versioning Strategy

| Artifact | Scheme | Notes |
|---|---|---|
| Software | semver (git tags) | pyproject version |
| Schemas | semver; additive changes = minor | Breaking changes require migration note |
| Criteria register | semver + `authorised_by` + freeze date | Campaign pins exact version; no in-place edits (new version instead) |
| Scoring rubric | semver | Referenced by register |
| Prompts | per-prompt semver + CHANGELOG | Recorded in every artifact |
| Models | pinned ids (provider + snapshot) | Temperature/top_p pinned |
| Campaign | immutable config bundle (hash) | Audit log references the hash |

Assessments are always reproducible: `campaign_config_hash` → exact criteria, rubric, prompts, models, thresholds.

---

## 26. Implementation Roadmap

Small, independently testable increments; each ends in a demo-able, reviewable state.

1. **Increment 1 — Ingestion spine:** packet intake, page classification (deterministic rules), rendering, provenance model, packet JSON output. Test: all 7 corpus packets → correct PacketModels (known page-type ground truth from this analysis).
2. **Increment 2 — OCR + SourceText:** text-layer + OCR paths, word boxes, confidence, column ordering, quote↔bbox resolution. Test: golden OCR accuracy on corpus pages; quote highlight demo.
3. **Increment 3 — Deterministic verification core:** quote verification, duplicate merge, date normalisation, alias registry v0. Unit tests + corpus integration.
4. **Increment 4 — Extraction:** section identification + P3 evidence extraction with schema validation + quarantine flow. Golden-set build begins (1 packet fully curated → all 7).
5. **Increment 5 — Criteria Stage 0:** parser + register validation + human sign-off flow (YAML + PR review). **Blocked on receiving the authorised job spec/framework** (OPEN QUESTION Q1).
6. **Increment 6 — Mapping + Assessment:** retrieval, P5, P6, citation validation, confidence derivation.
7. **Increment 7 — Scoring + report:** rubric engine, gates, coverage; HTML review report with drill-down; audit reconstruction tool.
8. **Increment 8 — Fairness & robustness hardening:** perturbation tests, redaction fail-closed integration, error-handling matrix completion, performance pass.
9. **Increment 9 — Reviewer workflow v1:** override recording, campaign bundle freezing, retention/deletion tooling.

Each increment adds its audit events and regression goldens before the next begins.

---

## 27. Open Design Questions

| # | Question | Provisional position (assumption labelled) |
|---|---|---|
| Q1 | ~~Job specification / assessment framework status~~ **RESOLVED 2026-10-28.** Job spec received and cross-checked; framework E1–E4/D1–D5 authorised. Final weighting (owner revision, v1.1.0): E2 Design & making = 3, E3 Curiosity = 3, E1 Applied problem solving = 2, E4 Values = 2, D1–D5 = 1; PARTIAL band = 2; cover letters equal-status. E1's draft label "highest assessment priority" retired — weights are the single priority signal. Proposed E5/G1/G2 rejected by owner; the three corresponding spec essentials (enrolment, engineering background, Brackley) are recorded as intentionally not assessed. Frozen as `config/criteria/criteria-register-v1.1.0.yaml`, authorised by Chris Lettis, Head of Aero Design (v1.0.0 superseded same day, before any assessments were produced). | Stages 4–6 unblocked. Remaining optional items: official role title/duration for report headers; shortlisting policy (whether the weighted aggregate is used or reviewer bands decide) |
| Q2 | Is an enterprise-approved LLM endpoint available for candidate data? | **OPEN QUESTION.** ASSUMPTION (provisional): yes, eventually; until then development uses synthetic data + local models |
| Q3 | OCR engine choice (Tesseract vs PaddleOCR vs approved cloud OCR) | Provisional: local-first; decide via golden-set accuracy spike (Increment 2) |
| Q4 | Retention period and deletion scope for candidate data | **OPEN QUESTION** — needs HR/legal policy; provisional: fix at campaign definition |
| Q5 | Is numerical scoring wanted at all, or are bands + gates sufficient for reviewer decision support? | Provisional: both supported; weights optional in register |
| Q6 | Volume & parallelism of campaigns; multi-reviewer concurrency | ASSUMPTION: small scale → SQLite + batch runner adequate |
| Q7 | Should ATS export format be treated as stable (same ATS going forward)? | ASSUMPTION: yes for v1; page classifier designed to degrade gracefully otherwise |
| Q8 | Fairness monitoring: is aggregate equality analysis (e.g. outcome deltas across demographic groups) in scope? That would require protected-characteristic data we must NOT process in the pipeline — likely a separate, HR-owned process | Provisional: out of pipeline scope; flag to responsible-AI owner |
| Q9 | Are portfolio links (observed in corpus) ever to be fetched/assessed? | Provisional: `NOT_ACCESSIBLE`; fetching external content is out of scope v1 |
| Q10 | Reviewer identity/auth for overrides in v1 HTML report | Provisional: reviewer name field in v1; proper auth deferred |

---

## 28. Recommended First Implementation Increment

**Increment 1 (Packet intake & provenance)**, with two justifications from the corpus analysis: (a) everything downstream depends on correct page classification and provenance; (b) it is fully deterministic, needs no LLM approval (Q2), and is testable today against the 7 supplied packets.

Scope:
- CLI `cvreview ingest <pdf>` → `packet.json` + page PNGs + page-type labels (form/CV/letter/divider/blank/no-data) + duplicate groups + text-layer fields from page 1.
- Pydantic models for PacketModel/Document/Page; structlog events → audit JSONL; pytest suite incl. the corpus-derived edge cases (duplicates, orphaned page-3 fragment, blank/no-data pages).
- Acceptance: correct classification of all 39 corpus pages per §3.1 ground truth; duplicate groups found for `808_6934` (CV) and `808_9411` (letter); quoteable provenance object for every text region.

---

## Decision Log (consolidated)

| Decision | Reason | Alternatives | Trade-offs |
|---|---|---|---|
| Evidence-first with mandatory verbatim quotes + bbox provenance | Traceability requirement R1; corpus provenance needs (OCR errors, duplicates) | Direct document→score LLM | Slower, more infra; gains auditability, fairness testing, error isolation |
| Stage 0 criteria pipeline with human sign-off | No criteria supplied; prevents criteria drift (risk A1) | Embed raw job spec in prompts | Extra stage + UI; gains versioning, authorisation, auditability |
| OCR without LLM correction; normalise at value level | Preserves provenance integrity | LLM text cleanup | Raw text noisier; correctness handled downstream by verification |
| Deterministic scoring engine | R2/R8; scores must not drift with model mood | LLM scoring | Less "nuance"; nuance belongs in evidence_expectation + assessment classes |
| Null-not-zero for missing/conflicting evidence | R5 (missing ≠ failure) | Scoring 0 | Coverage % must accompany scores; prevents silent penalisation |
| Categorical rule-derived confidence | Calibrated, explainable, stable | Model probabilities | Coarser; requires threshold tuning |
| Packets not documents as ingestion unit | Corpus is ATS packets with junk/duplicates | Treat PDF as one doc | More ingestion logic; prevents double-counting and junk-page extraction |
| No LangChain; thin LLM client | Inspectability, versioning, audit | Framework adoption | More hand-rolled retry/validation code (small) |
| SQLite-first persistence | Campaign scale assumption | Postgres day 1 | Migration later if multi-user; schema kept portable |
| HTML report before interactive UI | Increment 7 deliverable value vs effort | React/Streamlit | Reviewers get drill-down quickly; interaction (overrides) minimally clunky in v1 |
| PyMuPDF (licence caveat) | Best rendering+boxes API | pypdfium2 | AGPL review needed for commercial use; fallback identified |

---

*End of plan. This document is the basis for technical review; implementation tasks should be carved from the Increment list in §26.*
