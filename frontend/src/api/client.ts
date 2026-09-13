/**
 * API 客户端 — 支持样例模式和真实模式切换
 *
 * 样例模式下直接返回 mock 数据，真实模式下调用后端 API。
 * 当前后端 HTTP 接口尚未实现（P06），先以样例模式为主。
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
  const res = await fetch(`/api${path}`, {
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
    form.append("question", question);
    return request<DocumentInfo>("/documents/upload", {
      method: "POST",
      headers: {}, // let browser set multipart boundary
      body: form,
    });
  });
}

/* ────────── 步骤2: 获取需补充的资料字段 ────────── */

export async function getProfileFields(
  docId: string
): Promise<UserProfileField[]> {
  if (_demoMode) {
    await _fakeDelay(300);
    return MOCK_PROFILE_FIELDS.map((f) => ({ ...f }));
  }

  return request<UserProfileField[]>(`/documents/${docId}/profile-fields`);
}

/** 提交补充资料 */
export async function submitProfile(
  docId: string,
  fields: Record<string, string>
): Promise<{ accepted: boolean; errors?: Record<string, string> }> {
  if (_demoMode) {
    await _fakeDelay(500);
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

  return dedup(`profile-${docId}`, () =>
    request(`/documents/${docId}/profile`, {
      method: "POST",
      body: JSON.stringify({ fields }),
    })
  );
}

/* ────────── 步骤3: 发起分析 & 查询状态 ────────── */

export async function startAnalysis(
  docId: string,
  question: string,
  profile: Record<string, string>
): Promise<AnalysisTask> {
  if (_demoMode) {
    await _fakeDelay(300);
    return { ...MOCK_TASK, status: "running", current_stage: "分析中…" };
  }

  return dedup(`analysis-${docId}`, () =>
    request<AnalysisTask>("/analysis/start", {
      method: "POST",
      body: JSON.stringify({ doc_id: docId, question, profile }),
    })
  );
}

export async function getAnalysisStatus(
  taskId: string
): Promise<AnalysisTask> {
  if (_demoMode) {
    await _fakeDelay(500);
    return { ...MOCK_TASK };
  }

  return request<AnalysisTask>(`/analysis/${taskId}/status`);
}

export async function getAnalysisResult(
  taskId: string
): Promise<AnalysisResult> {
  if (_demoMode) {
    await _fakeDelay(600);
    return { ...MOCK_ANALYSIS_RESULT };
  }

  return request<AnalysisResult>(`/analysis/${taskId}/result`);
}

export async function retryAnalysis(
  taskId: string
): Promise<AnalysisTask> {
  if (_demoMode) {
    await _fakeDelay(300);
    return { ...MOCK_TASK, status: "running", current_stage: "重新分析中…" };
  }

  return dedup(`retry-${taskId}`, () =>
    request<AnalysisTask>(`/analysis/${taskId}/retry`, { method: "POST" })
  );
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
  taskId: string
): Promise<ActionPlanItem[]> {
  if (_demoMode) {
    await _fakeDelay(400);
    return MOCK_ACTION_PLAN.map((a) => ({ ...a }));
  }

  return request<ActionPlanItem[]>(`/analysis/${taskId}/action-plan`);
}

export async function confirmAction(
  taskId: string,
  actionId: string
): Promise<ActionPlanItem> {
  if (_demoMode) {
    await _fakeDelay(300);
    const item = MOCK_ACTION_PLAN.find((a) => a.action_id === actionId);
    if (!item) throw { error_code: "NOT_FOUND", message: "操作不存在", user_message: "操作不存在", can_retry: false } satisfies ApiError;
    return { ...item, execution_status: "confirmed" };
  }

  return request<ActionPlanItem>(`/analysis/${taskId}/actions/${actionId}/confirm`, {
    method: "POST",
  });
}

/* ────────── 辅助 ────────── */

function _fakeDelay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
