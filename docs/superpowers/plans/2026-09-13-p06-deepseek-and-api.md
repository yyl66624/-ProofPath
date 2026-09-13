# P06 DeepSeek 与 HTTP 服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把模型调用从 Anthropic 迁移到 DeepSeek，并提供一套只返回核验后结果的 FastAPI HTTP 服务。

**Architecture:** `DeepSeekReasoner` 只负责检索、有限重试、模型回退和本地结构解析；`analyze_document` 继续作为唯一的核验编排边界。FastAPI 适配器使用进程内仓库保存文档、幂等键和任务，通过后台线程调用应用服务，并在序列化时补充原文定位地址。

**Tech Stack:** Python 3.11+（开发与容器使用 3.12）、openai 3.13.0、FastAPI 0.141.1、Uvicorn 0.52.4、python-multipart 0.0.32、pytest 9.1.1

## Global Constraints

- 默认模型必须是 `deepseek-flash`，失败或难例最终回退到 `deepseek-v4-pro`。
- 模型调用必须使用 OpenAI 兼容入口，默认 `https://api.deepseek.com`。
- 默认 `max_tokens=3000` 且不得低于 2000；默认通过 `extra_body={"thinking": {"type": "disabled"}}` 关闭思考。
- 解析只读取 `message.content`，不得将 `reasoning_content` 混入正文或引用。
- 空正文且 `finish_reason == "length"` 是可重试截断；非空但非法 JSON 是结构错误；两者使用不同错误类型。
- 每次分析的客户端重试总量最多 2 次，所有尝试总数必须有限。
- 分析超时默认 120 秒；首版只使用进程内状态，不引入数据库。
- 所有模型结果必须通过 `analyze_document` 间接进入 `verify_report`，HTTP 适配器不得直接返回模型输出。
- 上传上限默认 20 MiB；只接受 `.pdf`、`.txt`、`.md`。
- `pyproject.toml`、`README.md`、`.env.example` 是 A 终审的共享文件，交接时必须单独列出。

---

### Task 1: DeepSeek 推理调用与错误分类

**Files:**
- Modify: `tests/test_reasoner.py`
- Modify: `src/proofpath/reasoner.py`
- Modify: `src/proofpath/config.py`
- Modify: `src/proofpath/errors.py`

**Interfaces:**
- Consumes: `Bm25Index.search(question, top_k=...)`、`build_context(hits)`、`_parse_payload(raw, question, doc_id)`。
- Produces: `DeepSeekReasoner(client: Any | None = None, model: str = config.MODEL, fallback_model: str = config.FALLBACK_MODEL, max_retries: int = config.MODEL_MAX_RETRIES)`；`analyze(...) -> EligibilityReport`。
- Produces: `ModelOutputTruncatedError` 用于空正文截断；`MalformedModelOutputError` 用于非空非法 JSON；`ModelRefusedError` 与 `ReasonerUnavailableError` 保留。

- [ ] **Step 1: 用 OpenAI 兼容响应替换测试夹具并写请求形状失败测试**

```python
def test_sends_deepseek_request_shape(document, index):
    client = _FakeClient(_response(WELL_FORMED))
    DeepSeekReasoner(client=client).analyze("硕士补贴多少", document, index)
    request = client.calls[0]
    assert request["model"] == "deepseek-flash"
    assert request["max_tokens"] == 3000
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert request["messages"][0]["role"] == "system"
    assert "JSON" in request["messages"][0]["content"].upper()
```

- [ ] **Step 2: 运行单测并确认旧 `ClaudeReasoner` 导致 RED**

Run: `python -m pytest tests/test_reasoner.py::TestAnalyze::test_sends_deepseek_request_shape -q`

Expected: FAIL because `DeepSeekReasoner` does not exist or the request still uses Anthropic fields.

- [ ] **Step 3: 写最小 DeepSeek 调用实现**

```python
response = self._client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(question, context, profile)},
    ],
    response_format={"type": "json_object"},
    max_tokens=config.MAX_TOKENS,
    extra_body={"thinking": {"type": "disabled"}},
)
content = response.choices[0].message.content
```

- [ ] **Step 4: 写错误与重试失败测试**

```python
@pytest.mark.parametrize("exc", [APITimeoutError(...), RateLimitError(...), APIConnectionError(...)])
def test_transient_errors_retry_then_fallback(exc, document, index):
    client = _SequenceClient([exc, exc, _response(WELL_FORMED)])
    report = DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)
    assert report.verdicts
    assert [call["model"] for call in client.calls] == [
        "deepseek-flash", "deepseek-flash", "deepseek-v4-pro"
    ]

def test_empty_length_response_is_truncation(document, index):
    client = _SequenceClient([_response("", finish_reason="length")] * 3)
    with pytest.raises(ModelOutputTruncatedError):
        DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)

def test_nonempty_invalid_json_is_malformed(document, index):
    client = _SequenceClient([_response("not-json")] * 3)
    with pytest.raises(MalformedModelOutputError):
        DeepSeekReasoner(client=client).analyze("硕士补贴", document, index)
```

- [ ] **Step 5: 运行失败测试，确认分别由重试、回退和错误分类缺失而 RED**

Run: `python -m pytest tests/test_reasoner.py -q`

Expected: FAIL on the new DeepSeek request, retry sequence, truncation type, refusal and content-only assertions.

- [ ] **Step 6: 实现有限重试和稳定错误映射**

```python
models = [self._model] * self._max_retries + [self._fallback_model]
for attempt, model in enumerate(models):
    try:
        response = self._create_completion(model, messages)
        return self._parse_response(response, question, document.doc_id)
    except _RETRYABLE_ERRORS as exc:
        last_error = exc
        if attempt == len(models) - 1:
            raise _public_error(exc) from exc
raise ReasonerUnavailableError(f"model call failed: {last_error}")
```

The retryable set is limited to timeout, connection, rate limit, empty `length` truncation, and malformed output. Authentication, permission, bad request, unknown model, and explicit refusal fail immediately. Every response path reads only `choice.message.content`.

- [ ] **Step 7: 运行推理层测试并确认 GREEN**

Run: `python -m pytest tests/test_reasoner.py -q`

Expected: all tests pass; the fake client records no more than three attempts.

- [ ] **Step 8: 提交推理层变更**

```bash
git add tests/test_reasoner.py src/proofpath/reasoner.py src/proofpath/config.py src/proofpath/errors.py
git commit -m "feat(P06): migrate reasoner to DeepSeek"
```

### Task 2: CLI 切换与 Anthropic 过渡清理

**Files:**
- Modify: `tests/test_parsers_e2e.py`
- Modify: `src/proofpath/cli.py`
- Modify: `src/proofpath/demo.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/credentials.md`

**Interfaces:**
- Consumes: `DeepSeekReasoner` from Task 1。
- Produces: `proofpath check` 默认走 DeepSeek；`proofpath doctor` 报告 `openai` 而不是 `anthropic`；安装基础依赖不再包含 Anthropic。

- [ ] **Step 1: 写 CLI 行为失败测试**

```python
def test_doctor_reports_openai_sdk(capsys):
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "openai (DeepSeek 模型调用)" in output
    assert "anthropic" not in output.lower()
```

- [ ] **Step 2: 运行该测试并确认 RED**

Run: `python -m pytest tests/test_parsers_e2e.py::test_doctor_reports_openai_sdk -q`

Expected: FAIL because doctor still reports Anthropic.

- [ ] **Step 3: 切换 CLI 和文档依赖**

```python
from .reasoner import DeepSeekReasoner
reasoner = DeepSeekReasoner(model=args.model)
```

Delete `anthropic==1.4.0` from `pyproject.toml`, remove `ANTHROPIC_API_KEY` from `.env.example` and `docs/credentials.md`, remove the README transition warning, and update install/runtime wording to OpenAI SDK + DeepSeek.

- [ ] **Step 4: 运行 CLI 和推理层测试并确认 GREEN**

Run: `python -m pytest tests/test_reasoner.py tests/test_parsers_e2e.py -q`

Expected: all tests pass and no test imports Anthropic.

- [ ] **Step 5: 扫描残留并提交**

Run: `rg -n "ClaudeReasoner|ANTHROPIC_API_KEY|import anthropic|anthropic==" src tests pyproject.toml .env.example README.md docs/credentials.md`

Expected: no matches.

```bash
git add tests/test_parsers_e2e.py src/proofpath/cli.py src/proofpath/demo.py pyproject.toml .env.example README.md docs/credentials.md
git commit -m "chore(P06): remove Anthropic transition code"
```

### Task 3: FastAPI 文档上传与错误封装

**Files:**
- Create: `src/proofpath/api.py`
- Create: `tests/test_api.py`
- Modify: `src/proofpath/config.py`
- Modify: `docs/api-contract.md`

**Interfaces:**
- Consumes: `load_document(path) -> Document` and existing typed parser errors.
- Produces: `create_app(reasoner_factory=DeepSeekReasoner) -> FastAPI`；`POST /api/v1/documents`；`GET /api/v1/documents/{document_id}/pages/{page}`。
- Stores: immutable `Document` plus safe display metadata in an in-memory repository keyed by `document_id`.

- [ ] **Step 1: 写上传和原文页接口失败测试**

```python
def test_upload_text_and_get_page(client):
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("policy.txt", "第一条 申请条件", "text/plain")},
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    page = client.get(f"/api/v1/documents/{body['document_id']}/pages/1")
    assert page.status_code == 200
    assert page.json()["text"] == "第一条 申请条件"

def test_rejects_unsupported_upload(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("policy.exe", b"x", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
```

- [ ] **Step 2: 运行上传接口测试并确认 RED**

Run: `python -m pytest tests/test_api.py -q`

Expected: collection or request FAIL because `proofpath.api` does not exist.

- [ ] **Step 3: 实现应用工厂、进程内仓库和临时文件解析**

```python
def create_app(reasoner_factory=DeepSeekReasoner) -> FastAPI:
    app = FastAPI(title="ProofPath API", version="0.1.0")
    app.state.store = InMemoryStore()
    app.state.reasoner_factory = reasoner_factory
    return app
```

Upload handling must strip directory components with `Path(filename).name`, enforce `PROOFPATH_MAX_UPLOAD_BYTES` before parsing, create a private temporary directory, pass an explicit file path to `load_document`, and delete the temporary directory after the immutable document is loaded.

- [ ] **Step 4: 实现统一错误对象和原文页序列化**

```python
def error_response(status_code: int, code: str, message: str, retryable: bool, action: str):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message,
                            "retryable": retryable,
                            "suggested_action": action,
                            "request_id": new_request_id()}},
    )
```

Page responses use existing `document.chunks`, include only chunks whose one-based `page` equals the route page, and generate stable fragment IDs as `{document_id}-p{page}-c{index}`.

- [ ] **Step 5: 运行上传接口测试并确认 GREEN**

Run: `python -m pytest tests/test_api.py -q`

Expected: upload success, empty/oversize/unsupported/corrupt failures, page success and page/document not-found tests pass.

- [ ] **Step 6: 提交上传接口**

```bash
git add src/proofpath/api.py src/proofpath/config.py tests/test_api.py docs/api-contract.md
git commit -m "feat(P06): add document HTTP endpoints"
```

### Task 4: 分析任务、幂等、取消与安全序列化

**Files:**
- Modify: `src/proofpath/api.py`
- Modify: `tests/test_api.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `analyze_document(question, document, reasoner, profile=...) -> AnalysisOutcome`。
- Produces: `POST /api/v1/analyses`、`GET /api/v1/analyses/{analysis_id}`、`POST /api/v1/analyses/{analysis_id}/cancel`。
- Stores: canonical request fingerprint, task state, timestamps, result or stable public error; the key is retained for the process lifetime.

- [ ] **Step 1: 写分析成功、幂等冲突和取消失败测试**

```python
def test_create_analysis_returns_only_verified_result(client, uploaded_document):
    response = client.post(
        "/api/v1/analyses",
        headers={"Idempotency-Key": "same-request-key-1"},
        json={"document_id": uploaded_document, "question": "年龄条件", "profile": []},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["state"] in {"SUCCEEDED", "PARTIAL"}
    assert body["result"]["verdicts"][0]["citations"][0]["status"] == "VERIFIED"

def test_same_key_different_body_conflicts(client, uploaded_document):
    first = {"document_id": uploaded_document, "question": "年龄条件", "profile": []}
    second = {**first, "question": "学历条件"}
    client.post("/api/v1/analyses", headers={"Idempotency-Key": "conflict-key-1234"}, json=first)
    response = client.post("/api/v1/analyses", headers={"Idempotency-Key": "conflict-key-1234"}, json=second)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
```

- [ ] **Step 2: 运行分析接口测试并确认 RED**

Run: `python -m pytest tests/test_api.py -q`

Expected: FAIL because analysis routes and state storage are absent.

- [ ] **Step 3: 实现规范化、幂等与任务状态**

```python
canonical = json.dumps(request.model_dump(), ensure_ascii=False,
                       sort_keys=True, separators=(",", ":"))
fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Validate idempotency keys as 16–128 printable ASCII characters, trim questions to 1–2000 Unicode characters, reject duplicate profile keys, and cap profile length at 50. The first request creates one task; an identical replay returns the same task without calling the reasoner again; a changed fingerprint returns 409.

- [ ] **Step 4: 通过应用服务执行并序列化核验结果**

```python
outcome = analyze_document(question, document, reasoner, profile=profile_dict)
state = "PARTIAL" if (
    outcome.requires_human_review
    or any(v.status in {ConditionStatus.NEEDS_INPUT, ConditionStatus.UNKNOWN}
           for v in outcome.report.verdicts)
    or any(c.status is CitationStatus.PARTIAL
           for v in outcome.report.verdicts for c in v.citations)
) else "SUCCEEDED"
```

The result serializer returns `materials: []`, derives `missing_inputs` from `NEEDS_INPUT` verdicts, generates citation locators to the page endpoint, and never includes a raw model response. Typed parser/model failures map to stable errors without secrets or profile values.

- [ ] **Step 5: 实现 120 秒超时与迟到结果丢弃**

Use a bounded worker executor. When `PROOFPATH_ANALYZE_TIMEOUT_SECONDS` elapses, mark the task `FAILED` with `ANALYSIS_TIMEOUT`; when cancellation wins, mark `CANCELLED`. Before any worker writes a terminal result, acquire the store lock and confirm the task is still `RUNNING`; a cancelled or timed-out task ignores the late result.

- [ ] **Step 6: 运行 API 与服务层测试并确认 GREEN**

Run: `python -m pytest tests/test_api.py tests/test_service.py tests/test_reasoner.py -q`

Expected: all analysis, idempotency, state, cancellation, timeout, model-error and verifier-boundary tests pass.

- [ ] **Step 7: 提交分析接口**

```bash
git add src/proofpath/api.py tests/test_api.py tests/test_service.py
git commit -m "feat(P06): add verified analysis task API"
```

### Task 5: P06 完整验证与交接

**Files:**
- Modify: `docs/api-contract.md`
- Modify: `README.md`
- Inspect: all files changed since `origin/main`

**Interfaces:**
- Consumes: Tasks 1–4。
- Produces: 可由 D 接入、E 验收、A 终审与合并的 P06 分支。

- [ ] **Step 1: 对齐契约中的 120 秒超时和进程内限制**

Ensure `docs/api-contract.md` says the model timeout is 120 seconds and clearly states idempotency/task retention is process-local unless optional JSON persistence is enabled later.

- [ ] **Step 2: 运行受影响测试**

Run: `python -m pytest tests/test_reasoner.py tests/test_service.py tests/test_api.py tests/test_parsers_e2e.py -q`

Expected: all affected tests pass.

- [ ] **Step 3: 运行完整验证**

Run: `python -m pytest -q`

Expected: zero failures.

Run: `python -m pytest --cov=proofpath --cov-report=term-missing -q`

Expected: zero failures and no new safety-critical branch lacks coverage.

Run: `python -m compileall -q src tests`

Expected: exit 0.

Run: `python -m pip check`

Expected: `No broken requirements found.`

Run: `git diff --check`

Expected: exit 0 with no whitespace errors.

- [ ] **Step 4: 完成独立审查**

Review the diff against D-009 through D-013 and C-3 through C-14. Any Critical or Important finding must first receive a failing regression test, then the smallest fix, then the affected checks above.

- [ ] **Step 5: 准备 A/D/E 交接**

Report endpoint paths, startup command `uvicorn proofpath.api:app --host 127.0.0.1 --port 8000`, process-local persistence limitation, test counts, and every shared file requiring A approval. Ask D to wire against `docs/api-contract.md`; ask E to execute T04, T08 and failure-classification scenarios against this branch.

- [ ] **Step 6: 提交最终文档**

```bash
git add docs/api-contract.md README.md docs/superpowers/plans/2026-09-13-p06-deepseek-and-api.md
git commit -m "docs(P06): document backend integration and limits"
```
