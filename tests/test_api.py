"""HTTP contract tests for the P06 FastAPI adapter."""
from __future__ import annotations

import threading
import time
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

import proofpath.api as api_module
from proofpath.errors import (
    MalformedModelOutputError,
    ModelRateLimitedError,
    ReasonerUnavailableError,
)
from proofpath.models import (
    Citation,
    CitationStatus,
    ConditionStatus,
    ConditionVerdict,
    Document,
    EligibilityReport,
    VerifiedCitation,
)

POLICY_TEXT = "第一条 申请时年龄不超过35周岁。"
create_app = getattr(api_module, "create_app", None)


def test_api_factory_is_available() -> None:
    assert create_app is not None


def _unverified(page: int, quote: str) -> VerifiedCitation:
    return VerifiedCitation(
        citation=Citation(page=page, quote=quote),
        status=CitationStatus.NOT_FOUND,
        coverage=0.0,
    )


def _report(document: Document) -> EligibilityReport:
    return EligibilityReport(
        doc_id=document.doc_id,
        question="我28岁，符合年龄要求吗？",
        verdicts=(
            ConditionVerdict(
                condition="申请时年龄不超过35周岁",
                status=ConditionStatus.MET,
                rationale="模型生成的理由",
                citations=(_unverified(1, "申请时年龄不超过35周岁"),),
            ),
        ),
        checklist=("模型生成的材料",),
        summary="模型生成的总结",
    )


class _RecordingReasoner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def analyze(
        self,
        question: str,
        document: Document,
        index: object,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int,
    ) -> EligibilityReport:
        self.calls.append(
            {"question": question, "document": document, "profile": profile}
        )
        return _report(document)


class _FailingReasoner(_RecordingReasoner):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def analyze(self, *args: Any, **kwargs: Any) -> EligibilityReport:
        self.calls.append({"args": args, "kwargs": kwargs})
        raise self.error


class _BlockingReasoner(_RecordingReasoner):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def analyze(
        self,
        question: str,
        document: Document,
        index: object,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int,
    ) -> EligibilityReport:
        self.calls.append(
            {"question": question, "document": document, "profile": profile}
        )
        self.started.set()
        if not self.release.wait(timeout=2):
            raise RuntimeError("test did not release blocking reasoner")
        return _report(document)


class _RetryingUntilCancelledReasoner(_RecordingReasoner):
    """Models a provider wrapper that would retry unless API cancellation arrives."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release_first = threading.Event()
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.attempts = 0

    def cancel(self) -> None:
        self.cancelled.set()

    def analyze(
        self,
        question: str,
        document: Document,
        index: object,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int,
    ) -> EligibilityReport:
        for attempt in range(3):
            self.attempts += 1
            if attempt == 0:
                self.started.set()
                if not self.release_first.wait(timeout=2):
                    raise RuntimeError("test did not release first attempt")
            if self.cancelled.is_set():
                self.finished.set()
                raise RuntimeError("cancelled before retry")
        self.finished.set()
        return _report(document)


class _BlockingCancelReasoner(_RecordingReasoner):
    """Exposes whether a terminal state is published before cancellation."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.cancel_started = threading.Event()
        self.allow_cancel = threading.Event()
        self.stop_analysis = threading.Event()

    def cancel(self) -> None:
        self.cancel_started.set()
        if not self.allow_cancel.wait(timeout=2):
            raise RuntimeError("test did not release cancellation")
        self.stop_analysis.set()

    def analyze(
        self,
        question: str,
        document: Document,
        index: object,
        *,
        profile: dict[str, Any] | None = None,
        top_k: int,
    ) -> EligibilityReport:
        self.started.set()
        if not self.stop_analysis.wait(timeout=2):
            raise RuntimeError("test did not stop analysis")
        return _report(document)


@pytest.fixture
def reasoner() -> _RecordingReasoner:
    return _RecordingReasoner()


@pytest.fixture
def client(reasoner: _RecordingReasoner) -> Iterator[TestClient]:
    app = create_app(reasoner_factory=lambda: reasoner)
    with TestClient(app) as test_client:
        yield test_client


def _upload(
    client: TestClient,
    *,
    filename: str = "policy.txt",
    content: str = POLICY_TEXT,
    media_type: str = "text/plain",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, content.encode("utf-8"), media_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _analysis_body(document_id: str, question: str = "年龄条件") -> dict[str, Any]:
    return {
        "document_id": document_id,
        "question": question,
        "profile": [
            {"key": "年龄", "value": "28", "state": "PROVIDED", "source": "USER_INPUT"}
        ],
    }


def _wait_for_terminal(client: TestClient, analysis_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/analyses/{analysis_id}")
        assert response.status_code == 200
        task = response.json()
        if task["state"] != "RUNNING":
            return task
        time.sleep(0.005)
    raise AssertionError("analysis did not reach a terminal state")


class TestDocuments:
    def test_openapi_exposes_typed_request_and_response_contracts(
        self, client: TestClient
    ) -> None:
        schema = client.get("/openapi.json").json()
        paths = schema["paths"]
        upload_schema = paths["/api/v1/documents"]["post"]["responses"]["201"][
            "content"
        ]["application/json"]["schema"]
        analysis_request = paths["/api/v1/analyses"]["post"]["requestBody"][
            "content"
        ]["application/json"]["schema"]
        analysis_response = paths["/api/v1/analyses"]["post"]["responses"]["202"][
            "content"
        ]["application/json"]["schema"]

        assert upload_schema["$ref"].endswith("/DocumentResponse")
        assert analysis_request["$ref"].endswith("/AnalysisRequest")
        assert analysis_response["$ref"].endswith("/AnalysisTaskResponse")
        task_schema = schema["components"]["schemas"]["AnalysisTaskResponse"]
        assert {
            "analysis_id",
            "document_id",
            "state",
            "profile",
            "result",
            "error",
        } <= set(task_schema["required"])

    def test_upload_text_and_get_source_page(self, client: TestClient) -> None:
        document = _upload(client, filename="folder/../住房政策.txt")
        assert document["filename"] == "住房政策.txt"
        assert document["media_type"] == "text/plain"
        assert document["parser"] == "plaintext"
        assert document["page_count"] == 1
        assert document["created_at"].endswith("Z")

        response = client.get(
            f"/api/v1/documents/{document['document_id']}/pages/1"
        )
        assert response.status_code == 200
        page = response.json()
        assert page["document_id"] == document["document_id"]
        assert page["page"] == 1
        assert page["text"] == POLICY_TEXT
        assert page["fragments"][0] == {
            "fragment_id": f"{document['document_id']}-p1-c0",
            "document_id": document["document_id"],
            "page": 1,
            "text": POLICY_TEXT,
        }

    def test_windows_path_in_filename_is_sanitized(self, client: TestClient) -> None:
        document = _upload(client, filename="C:\\private\\policy.md")
        assert document["filename"] == "policy.md"
        assert document["media_type"] == "text/markdown"

    @pytest.mark.parametrize(
        "filename",
        [
            f"{'a' * 300}.txt",
            "policy#question?encoded%2Fname.txt",
        ],
    )
    def test_unsafe_display_filename_cannot_break_storage_or_locator(
        self, client: TestClient, filename: str
    ) -> None:
        document = _upload(client, filename=filename)
        assert document["filename"] == filename
        assert all(
            character.isascii() and (character.isalnum() or character in "-_")
            for character in document["document_id"]
        )
        page = client.get(
            f"/api/v1/documents/{document['document_id']}/pages/1"
        )
        assert page.status_code == 200

    def test_document_id_depends_on_content_not_display_filename(
        self, client: TestClient
    ) -> None:
        first = _upload(client, filename="first.txt")
        second = _upload(client, filename="second.txt")
        assert first["document_id"] == second["document_id"]

    @pytest.mark.parametrize(
        ("filename", "content", "expected_status", "expected_code"),
        [
            ("policy.exe", b"content", 415, "UNSUPPORTED_MEDIA_TYPE"),
            ("empty.txt", b"", 422, "EMPTY_FILE"),
            ("blank.txt", b"  \n", 422, "NO_EXTRACTABLE_TEXT"),
            ("damaged.txt", b"policy\xff\xfecontent", 422, "DOCUMENT_DAMAGED"),
        ],
    )
    def test_upload_failures_use_stable_error_envelope(
        self,
        client: TestClient,
        filename: str,
        content: bytes,
        expected_status: int,
        expected_code: str,
    ) -> None:
        response = client.post(
            "/api/v1/documents",
            files={"file": (filename, content, "application/octet-stream")},
        )
        assert response.status_code == expected_status
        assert set(response.json()) == {"error"}
        error = response.json()["error"]
        assert error["code"] == expected_code
        assert isinstance(error["retryable"], bool)
        assert error["suggested_action"]
        assert error["request_id"].startswith("req_")

    def test_rejects_file_over_configured_limit(self) -> None:
        app = create_app(
            reasoner_factory=_RecordingReasoner,
            max_upload_bytes=4,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/documents",
                files={"file": ("large.txt", b"12345", "text/plain")},
            )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"

    @pytest.mark.parametrize(
        ("path", "code"),
        [
            ("/api/v1/documents/not-found/pages/1", "DOCUMENT_NOT_FOUND"),
            ("/api/v1/documents/not-found/pages/0", "DOCUMENT_NOT_FOUND"),
        ],
    )
    def test_unknown_document_is_explicit(
        self, client: TestClient, path: str, code: str
    ) -> None:
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == code

    def test_page_out_of_range_is_explicit(self, client: TestClient) -> None:
        document = _upload(client)
        response = client.get(
            f"/api/v1/documents/{document['document_id']}/pages/2"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PAGE_NOT_FOUND"


class TestAnalyses:
    def test_verified_analysis_is_queryable_and_hides_model_materials(
        self, client: TestClient, reasoner: _RecordingReasoner
    ) -> None:
        document = _upload(client)
        response = client.post(
            "/api/v1/analyses",
            headers={"Idempotency-Key": "verified-case-0001"},
            json=_analysis_body(document["document_id"]),
        )
        assert response.status_code == 202
        accepted = response.json()
        assert accepted["analysis_id"].startswith("ana_")
        assert accepted["document_id"] == document["document_id"]

        task = _wait_for_terminal(client, accepted["analysis_id"])
        assert task["state"] == "PARTIAL"
        assert task["error"] is None
        assert task["result"]["materials"] == []
        assert task["result"]["requires_human_review"] is True
        verdict = task["result"]["verdicts"][0]
        assert verdict["citations"][0]["status"] == "VERIFIED"
        assert verdict["citations"][0]["fragment_id"].endswith("-p1-c0")
        assert verdict["citations"][0]["locator"].endswith("/pages/1")
        assert len(reasoner.calls) == 1
        assert reasoner.calls[0]["profile"] == {"年龄": "28"}

    def test_identical_idempotent_replay_returns_same_task_without_second_call(
        self, client: TestClient, reasoner: _RecordingReasoner
    ) -> None:
        document = _upload(client)
        request = _analysis_body(document["document_id"])
        headers = {"Idempotency-Key": "same-request-0001"}
        first = client.post("/api/v1/analyses", headers=headers, json=request)
        replay = client.post("/api/v1/analyses", headers=headers, json=request)
        assert first.status_code == 202
        assert replay.status_code == 200
        assert replay.json()["analysis_id"] == first.json()["analysis_id"]
        _wait_for_terminal(client, first.json()["analysis_id"])
        assert len(reasoner.calls) == 1

    def test_same_idempotency_key_with_different_request_conflicts(
        self, client: TestClient
    ) -> None:
        document = _upload(client)
        headers = {"Idempotency-Key": "conflict-case-01"}
        first = client.post(
            "/api/v1/analyses",
            headers=headers,
            json=_analysis_body(document["document_id"], "年龄条件"),
        )
        conflict = client.post(
            "/api/v1/analyses",
            headers=headers,
            json=_analysis_body(document["document_id"], "学历条件"),
        )
        assert first.status_code == 202
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    @pytest.mark.parametrize(
        ("key", "question"),
        [
            ("short", "年龄条件"),
            ("valid-key-0000001", "   "),
        ],
    )
    def test_invalid_analysis_request_is_a_400_error(
        self, client: TestClient, key: str, question: str
    ) -> None:
        document = _upload(client)
        response = client.post(
            "/api/v1/analyses",
            headers={"Idempotency-Key": key},
            json=_analysis_body(document["document_id"], question),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_duplicate_profile_keys_are_rejected(self, client: TestClient) -> None:
        document = _upload(client)
        body = _analysis_body(document["document_id"])
        body["profile"].append(
            {"key": " 年龄 ", "value": "29", "state": "PROVIDED", "source": "USER_INPUT"}
        )
        response = client.post(
            "/api/v1/analyses",
            headers={"Idempotency-Key": "duplicate-key-001"},
            json=body,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_unknown_document_and_analysis_are_explicit(self, client: TestClient) -> None:
        create = client.post(
            "/api/v1/analyses",
            headers={"Idempotency-Key": "unknown-doc-00001"},
            json=_analysis_body("missing-document"),
        )
        query = client.get("/api/v1/analyses/missing-analysis")
        cancel = client.post("/api/v1/analyses/missing-analysis/cancel")
        assert create.status_code == 404
        assert create.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
        assert query.status_code == 404
        assert query.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
        assert cancel.status_code == 404
        assert cancel.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"

    def test_cancellation_wins_over_late_model_result(self) -> None:
        reasoner = _BlockingReasoner()
        app = create_app(reasoner_factory=lambda: reasoner)
        with TestClient(app) as client:
            document = _upload(client)
            accepted = client.post(
                "/api/v1/analyses",
                headers={"Idempotency-Key": "cancel-case-00001"},
                json=_analysis_body(document["document_id"]),
            )
            assert accepted.status_code == 202
            assert reasoner.started.wait(timeout=1)
            analysis_id = accepted.json()["analysis_id"]
            cancelled = client.post(f"/api/v1/analyses/{analysis_id}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "CANCELLED"
            assert cancelled.json()["result"] is None
            reasoner.release.set()
            time.sleep(0.02)
            assert client.get(f"/api/v1/analyses/{analysis_id}").json()["state"] == "CANCELLED"

    def test_cancelling_terminal_task_does_not_erase_result(
        self, client: TestClient
    ) -> None:
        document = _upload(client)
        accepted = client.post(
            "/api/v1/analyses",
            headers={"Idempotency-Key": "terminal-case-001"},
            json=_analysis_body(document["document_id"]),
        )
        task = _wait_for_terminal(client, accepted.json()["analysis_id"])
        cancelled = client.post(
            f"/api/v1/analyses/{task['analysis_id']}/cancel"
        )
        assert cancelled.status_code == 200
        assert cancelled.json() == task


class TestAnalysisFailures:
    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (ModelRateLimitedError("provider detail"), "MODEL_RATE_LIMITED"),
            (MalformedModelOutputError("raw bad output"), "MODEL_OUTPUT_INVALID"),
            (ReasonerUnavailableError("secret profile value"), "MODEL_UNAVAILABLE"),
        ],
    )
    def test_model_failures_become_safe_terminal_tasks(
        self, error: Exception, code: str
    ) -> None:
        reasoner = _FailingReasoner(error)
        app = create_app(reasoner_factory=lambda: reasoner)
        with TestClient(app) as client:
            document = _upload(client)
            accepted = client.post(
                "/api/v1/analyses",
                headers={"Idempotency-Key": f"failure-{code.lower()}"},
                json=_analysis_body(document["document_id"]),
            )
            task = _wait_for_terminal(client, accepted.json()["analysis_id"])
        assert task["state"] == "FAILED"
        assert task["result"] is None
        assert task["error"]["code"] == code
        assert "provider detail" not in task["error"]["message"]
        assert "secret profile value" not in task["error"]["message"]

    def test_analysis_timeout_wins_over_late_result(self) -> None:
        reasoner = _BlockingReasoner()
        app = create_app(
            reasoner_factory=lambda: reasoner,
            analyze_timeout_seconds=0.02,
        )
        with TestClient(app) as client:
            document = _upload(client)
            accepted = client.post(
                "/api/v1/analyses",
                headers={"Idempotency-Key": "timeout-case-0001"},
                json=_analysis_body(document["document_id"]),
            )
            assert reasoner.started.wait(timeout=1)
            task = _wait_for_terminal(client, accepted.json()["analysis_id"])
            assert task["state"] == "FAILED"
            assert task["error"]["code"] == "MODEL_TIMEOUT"
            reasoner.release.set()
            time.sleep(0.02)
            unchanged = client.get(
                f"/api/v1/analyses/{task['analysis_id']}"
            ).json()
            assert unchanged["state"] == "FAILED"
            assert unchanged["error"]["code"] == "MODEL_TIMEOUT"

    def test_analysis_timeout_cancels_remaining_reasoner_retries(self) -> None:
        reasoner = _RetryingUntilCancelledReasoner()
        app = create_app(
            reasoner_factory=lambda: reasoner,
            analyze_timeout_seconds=0.02,
        )
        with TestClient(app) as client:
            document = _upload(client)
            accepted = client.post(
                "/api/v1/analyses",
                headers={"Idempotency-Key": "cancel-retries-01"},
                json=_analysis_body(document["document_id"]),
            )
            assert reasoner.started.wait(timeout=1)
            task = _wait_for_terminal(client, accepted.json()["analysis_id"])
            assert task["error"]["code"] == "MODEL_TIMEOUT"
            assert reasoner.cancelled.is_set()
            reasoner.release_first.set()
            assert reasoner.finished.wait(timeout=1)
            assert reasoner.attempts == 1

    def test_timeout_state_is_not_visible_before_cancel_signal_completes(self) -> None:
        reasoner = _BlockingCancelReasoner()
        app = create_app(
            reasoner_factory=lambda: reasoner,
            analyze_timeout_seconds=0.02,
        )
        with TestClient(app) as client:
            document = _upload(client)
            accepted = client.post(
                "/api/v1/analyses",
                headers={"Idempotency-Key": "atomic-timeout-01"},
                json=_analysis_body(document["document_id"]),
            )
            analysis_id = accepted.json()["analysis_id"]
            assert reasoner.started.wait(timeout=1)
            assert reasoner.cancel_started.wait(timeout=1)

            fetched: dict[str, Any] = {}
            finished = threading.Event()

            def fetch_task() -> None:
                fetched.update(
                    client.get(f"/api/v1/analyses/{analysis_id}").json()
                )
                finished.set()

            reader = threading.Thread(target=fetch_task)
            reader.start()
            assert not finished.wait(timeout=0.03)
            reasoner.allow_cancel.set()
            assert finished.wait(timeout=1)
            reader.join(timeout=1)
            assert fetched["state"] == "FAILED"
            assert fetched["error"]["code"] == "MODEL_TIMEOUT"
