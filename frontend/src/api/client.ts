/**
 * API 客户端 — 支持样例模式和真实模式切换
 *
 * 样例模式下直接返回 mock 数据，真实模式下调用后端 API。
 * 后端路径与 src/proofpath/api.py 的 P05 实现对齐。
 */
import type {
  DocumentInfo,
  UserProfileField,
  AnalysisResult,
  AnalysisTask,
  ActionPlanItem,
  ApiError,
} from "@/types";
import {
  MOCK_DOCUMENT,
  MOCK_PROFILE_FIELDS,
  MOCK_ANALYSIS_RESULT,
  MOCK_TASK,
  MOCK_ACTION_PLAN,
  MOCK_PAGE_TEXTS,
} from "@/mock/data";

/* ────────── 模式切换 ────────── */

let _demoMode = true;

export function isDemoMode(): boolean {
  return _demoMode;
}

export function setDemoMode(v: boolean): void {
  _demoMode = v;
}

/* ────────── 通用请求 ────────── */

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const body: ApiError = await res.json().catch(() => ({
      error_code: `HTTP_${res.status}`,
      message: res.statusText,
      user_message: "请求失败，请稍后重试",
      can_retry: res.status >= 500,
    }));
    throw body;
  }

  return res.json();
}

/** Build a 16–128 char Idempotency-Key as the API contract requires. */
function _idempotencyKey(prefix: string): string {
  // crypto.randomUUID gives 36 chars; padded with prefix to clear the 16-char floor.
  return `${prefix}-${crypto.randomUUID()}${Date.now().toString(36)}`.slice(0, 128);
}

/* ────────── 防重复提交 ────────── */

const _pendingRequests = new Map<string, Promise<unknown>>();

function dedup<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = _pendingRequests.get(key);
  if (existing) return existing as Promise<T>;

  const p = fn().finally(() => _pendingRequests.delete(key));
  _pendingRequests.set(key, p);
  return p;
}

/* ────────── 步骤1: 文件上传 ────────── */

export async function uploadDocument(
  file: File,
  question: string
): Promise<DocumentInfo> {
  if (_demoMode) {
    await _fakeDelay(800);
    return { ...MOCK_DOCUMENT };
  }

  return dedup(`upload-${file.name}`, async () => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentInfo>("/documents", {
      method: "POST",
      headers: { "X-File-Question": encodeURIComponent(question) },
      body: form,
    });
  });
}

/* ────────── 步骤2: 获取需补充的资料字段 ────────── */

export async function getProfileFields(
  _docId: string
): Promise<UserProfileField[]> {
  if (_demoMode) {
    await _fakeDelay(300);
    return MOCK_PROFILE_FIELDS.map((f) => ({ ...f }));
  }
  // 后端暂无该端点 — 真实模式也用 mock 以保持界面流程完整
  await _fakeDelay(300);
  return MOCK_PROFILE_FIELDS.map((f) => ({ ...f }));
}

/** 提交补充资料 */
export async function submitProfile(
  _docId: string,
  fields: Record<string, string>
): Promise<{ accepted: boolean; errors?: Record<string, string> }> {
  // 后端暂无该端点 — 真实模式本地校验（demo 模式走相同路径以保持一致）
  await _fakeDelay(300);
  const errors: Record<string, string> = {};
  for (const f of MOCK_PROFILE_FIELDS) {
    if (f.required && !fields[f.field_name]) {
      errors[f.field_name] = `请填写${f.label}`;
    }
  }
  return Object.keys(errors).length > 0
    ? { accepted: false, errors }
    : { accepted: true };
}

/* ────────── 步骤3: 发起分析 & 查询状态 ────────── */

type BackendAnalysisState = "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCELLED";

interface BackendAnalysesResponse {
  analysis_id: string;
  document_id: string;
  state: BackendAnalysisState;
  question: string;
  result: unknown;
  error: { code: string; message: string } | null;
  created_at: string;
  updated_at: string;
}

const _BACKEND_TO_FRONTEND_STATE: Record<BackendAnalysisState, AnalysisTask["status"]> = {
  RUNNING: "running",
  SUCCEEDED: "success",
  PARTIAL: "partial",
  FAILED: "failed",
  CANCELLED: "failed", // 前端没有 cancelled，归一化为 failed 展示
};

function _toFrontendTask(r: BackendAnalysesResponse, docId: string): AnalysisTask {
  const status = _BACKEND_TO_FRONTEND_STATE[r.state] ?? "idle";
  return {
    task_id: r.analysis_id,
    doc_id: docId,
    status,
    current_stage: r.state === "RUNNING" ? "分析中…" : r.state,
    updated_at: r.updated_at,
    can_retry: r.state === "FAILED" || r.state === "CANCELLED",
    error_code: r.error?.code,
    error_message: r.error?.message,
  };
}

export async function startAnalysis(
  docId: string,
  question: string,
  profile: Record<string, string>
): Promise<AnalysisTask> {
  if (_demoMode) {
    await _fakeDelay(300);
    return { ...MOCK_TASK, status: "running", current_stage: "分析中…" };
  }

  // 后端 /api/v1/analyses 的请求体：
  //   { document_id, question, profile: [{ key, value, state, source }] }
  const profileList = Object.entries(profile).map(([key, value]) => ({
    key,
    value,
    state: "PROVIDED" as const,
    source: "USER_INPUT" as const,
  }));

  return dedup(`analysis-${docId}`, async () => {
    const r = await request<BackendAnalysesResponse>("/analyses", {
      method: "POST",
      headers: { "Idempotency-Key": _idempotencyKey("web") },
      body: JSON.stringify({
        document_id: docId,
        question,
        profile: profileList,
      }),
    });
    return _toFrontendTask(r, docId);
  });
}

export async function getAnalysisStatus(
  taskId: string
): Promise<AnalysisTask> {
  if (_demoMode) {
    await _fakeDelay(500);
    return { ...MOCK_TASK };
  }

  const r = await request<BackendAnalysesResponse>(`/analyses/${taskId}`);
  return _toFrontendTask(r, r.document_id);
}

export async function getAnalysisResult(
  taskId: string
): Promise<AnalysisResult> {
  if (_demoMode) {
    await _fakeDelay(600);
    return { ...MOCK_ANALYSIS_RESULT };
  }
  const r = await request<BackendAnalysesResponse>(`/analyses/${taskId}`);
  const resultRaw = r.result as {
    summary?: string;
    verdicts?: Array<{
      condition: string;
      status: string;
      rationale?: string;
      citations?: Array<{ page: number; quote: string; status: string; coverage: number }>;
      missing_info?: string[];
    }>;
    materials?: string[];
    missing_inputs?: string[];
    requires_human_review?: boolean;
  } | null;
  if (!resultRaw) {
    throw {
      error_code: "RESULT_NOT_READY",
      message: "分析尚未完成或失败",
      user_message: "分析尚未完成，请稍候或返回上一步重试",
      can_retry: true,
    } satisfies ApiError;
  }
  return _toFrontendResult(r, resultRaw);
}

export async function retryAnalysis(
  taskId: string
): Promise<AnalysisTask> {
  if (_demoMode) {
    await _fakeDelay(300);
    return { ...MOCK_TASK, status: "running", current_stage: "重新分析中…" };
  }
  // 后端用 cancel + 重建流程；这里直接 cancel 后让用户重走上传
  await request(`/analyses/${taskId}/cancel`, { method: "POST" });
  return { ...MOCK_TASK, status: "failed", current_stage: "已取消，请重新发起" };
}

/* ────────── 步骤4: 原文与证据定位 ────────── */

export async function getPageText(
  docId: string,
  page: number
): Promise<{ page: number; text: string }> {
  if (_demoMode) {
    await _fakeDelay(200);
    const text = MOCK_PAGE_TEXTS[page];
    if (!text) throw { error_code: "PAGE_NOT_FOUND", message: `第${page}页不存在`, user_message: `第${page}页不存在`, can_retry: false } satisfies ApiError;
    return { page, text };
  }
  return request(`/documents/${docId}/pages/${page}`);
}

/* ────────── P10: 操作计划 ────────── */

export async function getActionPlan(
  _taskId: string
): Promise<ActionPlanItem[]> {
  if (_demoMode) {
    await _fakeDelay(400);
    return MOCK_ACTION_PLAN.map((a) => ({ ...a }));
  }
  // 后端暂无该端点 — 真实模式用 mock 以保持界面流程
  await _fakeDelay(400);
  return MOCK_ACTION_PLAN.map((a) => ({ ...a }));
}

export async function confirmAction(
  _taskId: string,
  actionId: string
): Promise<ActionPlanItem> {
  if (_demoMode) {
    await _fakeDelay(300);
    const item = MOCK_ACTION_PLAN.find((a) => a.action_id === actionId);
    if (!item) throw { error_code: "NOT_FOUND", message: "操作不存在", user_message: "操作不存在", can_retry: false } satisfies ApiError;
    return { ...item, execution_status: "confirmed" };
  }
  // 后端暂无该端点 — 真实模式本地确认
  const item = MOCK_ACTION_PLAN.find((a) => a.action_id === actionId);
  if (!item) throw { error_code: "NOT_FOUND", message: "操作不存在", user_message: "操作不存在", can_retry: false } satisfies ApiError;
  return { ...item, execution_status: "confirmed" };
}

/* ────────── 辅助 ────────── */

function _fakeDelay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 把后端 analyses 响应转为前端的 AnalysisResult 形状 */
function _toFrontendResult(
  r: BackendAnalysesResponse,
  raw: {
    summary?: string;
    verdicts?: Array<{
      condition: string;
      status: string;
      rationale?: string;
      citations?: Array<{ page: number; quote: string; status: string; coverage: number }>;
      missing_info?: string[];
    }>;
    materials?: string[];
    missing_inputs?: string[];
    requires_human_review?: boolean;
  }
): AnalysisResult {
  const verdicts = (raw.verdicts ?? []).map((v) => ({
    condition: v.condition,
    status: v.status as "MET" | "UNMET" | "NEEDS_INPUT" | "UNKNOWN",
    rationale: v.rationale ?? "",
    citations: (v.citations ?? []).map((c) => ({
      citation: { page: c.page, quote: c.quote },
      status: c.status as "VERIFIED" | "PARTIAL" | "NOT_FOUND" | "TOO_SHORT" | "BAD_PAGE",
      coverage: c.coverage,
    })),
    missing_info: v.missing_info ?? [],
  }));

  // 从 verdicts 推算 verification summary
  let verified = 0, partial = 0, rejected = 0;
  for (const v of verdicts) {
    for (const c of v.citations) {
      if (c.status === "VERIFIED") verified++;
      else if (c.status === "PARTIAL") partial++;
      else rejected++;
    }
  }

  return {
    task: _toFrontendTask(r, r.document_id),
    report: {
      doc_id: r.document_id,
      question: r.question,
      verdicts,
      checklist: raw.materials ?? [],
      summary: raw.summary ?? "",
    },
    verification: {
      total_citations: verdicts.reduce((n, v) => n + v.citations.length, 0),
      verified,
      partial,
      rejected,
      downgraded_conditions: verdicts.filter(
        (v) => v.status === "UNKNOWN" && v.citations.length > 0
      ).length,
    },
  };
}
