/**
 * ProofPath 前端类型定义
 *
 * 对齐后端 models.py 中的不可变领域类型，字段命名使用 snake_case
 * 保持与 Python 后端的一致性。
 */

/* ────────── 枚举 ────────── */

/** 条件判断状态 — 对齐 models.ConditionStatus */
export type ConditionStatus = "MET" | "UNMET" | "NEEDS_INPUT" | "UNKNOWN";

/** 引用核验状态 — 对齐 models.CitationStatus */
export type CitationStatus =
  | "VERIFIED"
  | "PARTIAL"
  | "NOT_FOUND"
  | "TOO_SHORT"
  | "BAD_PAGE";

/** 动作风险等级 — 对齐 models.RiskLevel */
export type RiskLevel = "READ_ONLY" | "LOCAL_WRITE" | "SENSITIVE";

/** 文档处理状态 */
export type DocumentStatus =
  | "uploading"
  | "parsing"
  | "ready"
  | "unsupported"
  | "error";

/** 分析任务状态 */
export type AnalysisStatus =
  | "idle"
  | "running"
  | "success"
  | "partial"
  | "failed";

/** 操作执行状态 */
export type ActionExecutionStatus =
  | "pending"
  | "confirmed"
  | "executing"
  | "done"
  | "cancelled"
  | "failed";

/* ────────── 数据对象 ────────── */

/** 文档 — 对齐 models.Document */
export interface DocumentInfo {
  doc_id: string;
  filename: string;
  format: string;
  status: DocumentStatus;
  page_count: number;
  content_hash?: string;
  error_message?: string;
}

/** 原文片段 — 对齐 models.Chunk */
export interface Chunk {
  chunk_id: string;
  doc_id: string;
  page: number;
  text: string;
}

/** 引用 — 对齐 models.Citation */
export interface Citation {
  page: number;
  quote: string;
}

/** 核验后的引用 — 对齐 models.VerifiedCitation */
export interface VerifiedCitation {
  citation: Citation;
  status: CitationStatus;
  coverage: number;
}

/** 用户资料字段 */
export interface UserProfileField {
  field_name: string;
  label: string;
  value: string;
  source: "user_input" | "not_provided" | "unwilling";
  required: boolean;
  error?: string;
}

/** 条件判断 — 对齐 models.ConditionVerdict */
export interface ConditionVerdict {
  condition: string;
  status: ConditionStatus;
  rationale: string;
  citations: VerifiedCitation[];
  missing_info: string[];
}

/** 材料项 */
export interface ChecklistItem {
  name: string;
  required: boolean;
  source: string;
  provided: boolean;
}

/** 分析任务 */
export interface AnalysisTask {
  task_id: string;
  doc_id: string;
  status: AnalysisStatus;
  current_stage?: string;
  updated_at: string;
  error_message?: string;
  error_code?: string;
  can_retry: boolean;
}

/** 资格报告 — 对齐 models.EligibilityReport */
export interface EligibilityReport {
  doc_id: string;
  question: string;
  verdicts: ConditionVerdict[];
  checklist: string[];
  summary: string;
}

/** 核验摘要 */
export interface VerificationSummary {
  total_citations: number;
  verified: number;
  partial: number;
  rejected: number;
  downgraded_conditions: number;
}

/** 操作计划项 */
export interface ActionPlanItem {
  action_id: string;
  target_url: string;
  action_type: string;
  field_name: string;
  field_value: string;
  value_source: string;
  risk_level: RiskLevel;
  execution_status: ActionExecutionStatus;
  requires_confirmation: boolean;
}

/* ────────── API 错误 ────────── */

/** 统一错误响应 */
export interface ApiError {
  error_code: string;
  message: string;
  user_message: string;
  can_retry: boolean;
  suggested_action?: string;
  field_errors?: Record<string, string>;
  request_id?: string;
}

/* ────────── 分析结果（含核验摘要） ────────── */

export interface AnalysisResult {
  task: AnalysisTask;
  report: EligibilityReport | null;
  verification: VerificationSummary | null;
}

/* ────────── 页面步骤状态 ────────── */

export type WizardStep =
  | "upload"     // 步骤1: 文件与问题输入
  | "profile"    // 步骤2: 资料补充
  | "analysis"   // 步骤3: 分析结果
  | "evidence";  // 步骤4: 原文与行动
