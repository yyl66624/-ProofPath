# C Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reviewable P05 API contract and a framework-neutral service that never exposes an unverified model report.

**Architecture:** Keep HTTP transport, persistence, and background execution outside the existing domain modules. Add one application-service boundary that composes retrieval, reasoning, document identity validation, and citation verification; a future HTTP adapter can serialize only the returned verified outcome.

**Tech Stack:** Python 3.11+, frozen dataclasses, typing protocols, pytest; no new runtime dependency in this increment.

## Global Constraints

- Reuse `parsers`, `retrieval`, `reasoner`, and `verifier`; do not create a second implementation of citation verification.
- A definite verdict may reach a caller only after `verify_report` has processed it.
- Reject a report whose `doc_id` differs from the source document to prevent cross-document evidence mixing.
- Derive the public summary from verified statuses and suppress untraced material strings.
- Until C-8 semantic support checking exists, flag every surviving definite verdict for human review.
- Keep service-side model credentials out of request/response objects, logs, fixtures, and repository files.
- Treat browser execution and semantic entailment checking as later, separately reviewed trust-boundary changes.

---

### Task 1: P05 API Contract Draft

**Files:**
- Create: `docs/api-contract.md`

**Interfaces:**
- Consumes: P03's future scenario choice and acceptance examples through contract review; this draft makes no assumption about a specific policy domain.
- Produces: Versioned JSON shapes and endpoint semantics for `POST /api/v1/documents`, `POST /api/v1/analyses`, `GET /api/v1/analyses/{analysis_id}`, and `GET /api/v1/documents/{document_id}/pages/{page}`.

- [x] **Step 1: Write the contract draft**

Define document, profile field, condition verdict, citation, material item, analysis task, error, and action-plan objects. Include request/response examples, state transitions, idempotency behavior, file constraints, retry guidance, and the rule that only verified results are returned.

- [x] **Step 2: Inspect the document for internal consistency**

Run:

```bash
rg -n "MET|UNMET|NEEDS_INPUT|UNKNOWN|RUNNING|SUCCEEDED|PARTIAL|FAILED|CANCELLED|idempot" docs/api-contract.md
```

Expected: every enum and idempotency rule is explicitly defined and used consistently.

- [x] **Step 3: Review the diff**

Run:

```bash
git diff --check -- docs/api-contract.md
git diff -- docs/api-contract.md
```

Expected: no whitespace errors; the diff contains only the new contract.

### Task 2: Verified Analysis Service Boundary

**Files:**
- Create: `src/proofpath/service.py`
- Modify: `src/proofpath/errors.py`
- Modify: `src/proofpath/models.py`
- Create: `tests/test_service.py`
- Modify: `tests/test_verifier.py`

**Interfaces:**
- Consumes: `Document`, `EligibilityReport`, `Bm25Index`, a reasoner implementing `analyze(question, document, index, *, profile, top_k)`, and `verify_report`.
- Produces: `analyze_document(question, document, reasoner, *, profile=None, top_k=DEFAULT_TOP_K) -> AnalysisOutcome`, where `AnalysisOutcome.report` has location-verified verdicts, a derived summary, no untraced checklist strings, and `requires_human_review` remains true until semantic support is checked.

- [x] **Step 1: Write failing trust-boundary tests**

```python
def test_fabricated_model_citation_is_downgraded_before_return(document):
    outcome = analyze_document("追补政策", document, _ReasonerWithFabricatedCitation())
    assert outcome.report.verdicts[0].status is ConditionStatus.UNKNOWN
    assert outcome.verification.downgraded_conditions == 1


def test_report_for_another_document_is_rejected(document):
    with pytest.raises(ReportDocumentMismatchError):
        analyze_document("学历要求", document, _ReasonerForDocument("another-doc"))


def test_unverified_summary_and_checklist_are_not_exposed(document):
    outcome = analyze_document("年龄要求", document, _ReasonerWithUnsafeProse())
    assert "一定符合" not in outcome.report.summary
    assert outcome.report.checklist == ()


def test_definite_verdict_requires_human_review(document):
    outcome = analyze_document("年龄要求", document, _ReasonerWithValidCitation())
    assert outcome.requires_human_review is True
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_service.py -q
```

Expected: collection fails because `proofpath.service` and `ReportDocumentMismatchError` do not exist.

- [x] **Step 3: Add the minimal service implementation**

```python
@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    report: EligibilityReport
    verification: VerificationSummary
    requires_human_review: bool


def analyze_document(question, document, reasoner, *, profile=None, top_k=DEFAULT_TOP_K):
    index = Bm25Index.from_document(document)
    proposed = reasoner.analyze(
        question, document, index, profile=profile, top_k=top_k
    )
    if proposed.doc_id != document.doc_id:
        raise ReportDocumentMismatchError(document.doc_id, proposed.doc_id)
    _validate_proposed_report(proposed)
    report, verification = verify_report(proposed, document)
    requires_human_review = any(
        verdict.status in (ConditionStatus.MET, ConditionStatus.UNMET)
        for verdict in report.verdicts
    )
    safe_report = replace(
        report,
        summary=_safe_summary(
            report, requires_human_review=requires_human_review
        ),
        checklist=(),
    )
    return AnalysisOutcome(
        report=safe_report,
        verification=verification,
        requires_human_review=requires_human_review,
    )
```

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_service.py -q
```

Expected: all service tests pass.

- [x] **Step 5: Run affected and full regression suites**

Run:

```bash
.venv/bin/python -m pytest tests/test_service.py tests/test_reasoner.py tests/test_verifier.py -q
.venv/bin/python -m pytest -q --cov
```

Expected: service, reasoner, verifier, and all repository tests pass with no regressions.

- [x] **Step 6: Review trust-boundary diff**

Run:

```bash
git diff --check
git diff -- src/proofpath/service.py src/proofpath/errors.py tests/test_service.py
```

Expected: no whitespace errors; every service return path passes through `verify_report`, and document identity is checked before verification.
