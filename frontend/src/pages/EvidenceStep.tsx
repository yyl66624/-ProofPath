/**
 * 步骤4: 原文与行动
 *
 * 左侧：原文页面（带证据高亮定位）
 * 右侧：行动计划（P10 受控填表）
 *
 * 定位成功与失败都有明确反馈（D-5）。
 * 核验未通过的引用不显示为已验证。
 * SENSITIVE 操作需要确认才能执行（actions.py 三级闸门）。
 */
import { useState, useCallback, useEffect, useRef } from "react";
import {
  ArrowLeft,
  FileText,
  MapPin,
  MapPinOff,
  Shield,
  ShieldAlert,
  ShieldCheck as ShieldCheckIcon,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { useApp } from "@/store/AppContext";
import { getPageText, getActionPlan, confirmAction } from "@/api/client";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";
import { CitationBadge } from "@/components/CitationBadge";
import type {
  VerifiedCitation,
  ActionPlanItem,
  RiskLevel,
  ApiError,
} from "@/types";

export function EvidenceStep() {
  const { state, dispatch, goBack } = useApp();
  const { analysisResult, document: doc } = state;

  const report = analysisResult?.report;

  /* ── 所有引用提取 ── */
  const allCitations: (VerifiedCitation & { conditionIdx: number })[] =
    report?.verdicts.flatMap((v, ci) =>
      v.citations.map((vc) => ({ ...vc, conditionIdx: ci }))
    ) ?? [];

  /* ── 当前选中引用 ── */
  const [selectedIdx, setSelectedIdx] = useState(0);
  const selected = allCitations[selectedIdx] ?? null;

  /* ── 页面文本 ── */
  const [pageText, setPageText] = useState<string | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(selected?.citation.page ?? 1);
  const highlightRef = useRef<HTMLSpanElement>(null);

  /* ── 行动计划 ── */
  const [actionPlan, setActionPlan] = useState<ActionPlanItem[]>([]);
  const [actionLoading, setActionLoading] = useState(false);

  /* ── 加载页面文本 ── */
  const loadPage = useCallback(
    async (page: number) => {
      if (!doc) return;
      setPageLoading(true);
      setPageError(null);

      try {
        const result = await getPageText(doc.doc_id, page);
        setPageText(result.text);
        setCurrentPage(page);
      } catch (err) {
        const apiErr = err as ApiError;
        setPageError(apiErr.user_message || `无法加载第${page}页`);
        setPageText(null);
      } finally {
        setPageLoading(false);
      }
    },
    [doc]
  );

  /* ── 选中引用时加载对应页面 ── */
  useEffect(() => {
    if (selected) {
      loadPage(selected.citation.page);
    }
  }, [selectedIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── 高亮滚动 ── */
  useEffect(() => {
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [pageText, selectedIdx]);

  /* ── 加载行动计划 ── */
  useEffect(() => {
    if (!analysisResult?.task.task_id) return;
    setActionLoading(true);
    getActionPlan(analysisResult.task.task_id)
      .then((plan) => {
        setActionPlan(plan);
        dispatch({ type: "SET_ACTION_PLAN", plan });
      })
      .catch(() => {
        /* 行动计划是可选功能，不阻塞页面 */
      })
      .finally(() => setActionLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── 确认操作 ── */
  const handleConfirm = useCallback(
    async (actionId: string) => {
      if (!analysisResult) return;
      try {
        const updated = await confirmAction(
          analysisResult.task.task_id,
          actionId
        );
        setActionPlan((prev) =>
          prev.map((a) => (a.action_id === actionId ? updated : a))
        );
      } catch (err) {
        const apiErr = err as ApiError;
        alert(apiErr.user_message || "确认失败");
      }
    },
    [analysisResult]
  );

  if (!report) {
    return (
      <div className="max-w-2xl mx-auto">
        <ErrorAlert
          message="没有可用的分析结果"
          actions={[{ label: "返回分析", onClick: goBack }]}
        />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      {/* 返回按钮 */}
      <button
        type="button"
        onClick={goBack}
        className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回分析结果
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ──────── 左侧：原文与引用定位 ──────── */}
        <div className="lg:col-span-3 space-y-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <FileText className="w-5 h-5 text-brand-600" aria-hidden="true" />
            原文定位
          </h3>

          {/* 引用选择器 */}
          <div className="flex flex-wrap gap-2">
            {allCitations.map((vc, idx) => {
              const isActive = idx === selectedIdx;
              const isTrustworthy =
                vc.status === "VERIFIED" || vc.status === "PARTIAL";

              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setSelectedIdx(idx)}
                  aria-current={isActive ? "true" : undefined}
                  className={`
                    inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium
                    rounded-md border transition-colors
                    ${isActive
                      ? isTrustworthy
                        ? "bg-green-100 border-green-300 text-green-800"
                        : "bg-red-100 border-red-300 text-red-800"
                      : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50"
                    }
                  `}
                >
                  {isTrustworthy ? (
                    <MapPin className="w-3 h-3" aria-hidden="true" />
                  ) : (
                    <MapPinOff className="w-3 h-3" aria-hidden="true" />
                  )}
                  引用 {idx + 1}
                </button>
              );
            })}
          </div>

          {/* 当前引用信息 */}
          {selected && (
            <div
              className={`p-3 rounded-lg border text-sm ${
                selected.status === "VERIFIED" || selected.status === "PARTIAL"
                  ? "bg-green-50 border-green-200"
                  : "bg-red-50 border-red-200"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <CitationBadge
                  status={selected.status}
                  coverage={selected.coverage}
                />
                <span className="text-xs text-gray-500">
                  第 {selected.citation.page} 页 · 条件 {selected.conditionIdx + 1}
                </span>
              </div>
              <p className="text-gray-700 italic">
                "{selected.citation.quote}"
              </p>
              {(selected.status === "NOT_FOUND" ||
                selected.status === "TOO_SHORT" ||
                selected.status === "BAD_PAGE") && (
                <p className="mt-2 text-xs text-red-600 flex items-start gap-1.5">
                  <MapPinOff className="w-3 h-3 shrink-0 mt-0.5" aria-hidden="true" />
                  {selected.status === "NOT_FOUND" &&
                    "此引用未能在原文指定页面找到，对应结论已降级为“原文未明确”。"}
                  {selected.status === "TOO_SHORT" &&
                    "此引用过短（不足以作为可靠证据），对应结论已降级。"}
                  {selected.status === "BAD_PAGE" &&
                    "引用所指页码在文档中不存在。"}
                </p>
              )}
            </div>
          )}

          {/* 翻页 */}
          {doc && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={currentPage <= 1}
                onClick={() => loadPage(currentPage - 1)}
                className="p-1.5 rounded-md border border-gray-300 hover:bg-gray-50 disabled:opacity-40 transition-colors"
                aria-label="上一页"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-gray-600">
                第 {currentPage} / {doc.page_count} 页
              </span>
              <button
                type="button"
                disabled={currentPage >= doc.page_count}
                onClick={() => loadPage(currentPage + 1)}
                className="p-1.5 rounded-md border border-gray-300 hover:bg-gray-50 disabled:opacity-40 transition-colors"
                aria-label="下一页"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* 原文内容 */}
          <div className="border border-gray-200 rounded-lg bg-white min-h-[300px] max-h-[500px] overflow-auto">
            {pageLoading ? (
              <LoadingSpinner message="加载原文…" />
            ) : pageError ? (
              <div className="p-4">
                <ErrorAlert
                  title="定位失败"
                  message={pageError}
                  canRetry
                  onRetry={() => loadPage(currentPage)}
                />
              </div>
            ) : pageText ? (
              <pre className="p-4 text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                {renderHighlightedText(
                  pageText,
                  selected?.citation.page === currentPage
                    ? selected.citation.quote
                    : null,
                  selected?.status === "VERIFIED" || selected?.status === "PARTIAL",
                  highlightRef
                )}
              </pre>
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-gray-400 py-12">
                选择一条引用以查看原文定位
              </div>
            )}
          </div>
        </div>

        {/* ──────── 右侧：行动计划 (P10) ──────── */}
        <div className="lg:col-span-2 space-y-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Shield className="w-5 h-5 text-brand-600" aria-hidden="true" />
            行动计划
          </h3>

          {actionLoading ? (
            <LoadingSpinner message="加载行动计划…" />
          ) : actionPlan.length === 0 ? (
            <div className="p-6 border border-dashed border-gray-300 rounded-lg text-center">
              <p className="text-sm text-gray-400">暂无可用的行动计划</p>
              <p className="text-xs text-gray-400 mt-1">
                受控填表功能为可选扩展
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {actionPlan.map((action, idx) => (
                <ActionCard
                  key={action.action_id}
                  action={action}
                  index={idx + 1}
                  onConfirm={handleConfirm}
                />
              ))}
              <p className="text-xs text-gray-500 mt-3 p-2 bg-gray-50 rounded">
                所有 SENSITIVE 操作在你确认前不会执行。
                确认后的操作不可自动撤销。
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ────────── 行动卡片 ────────── */

const RISK_CONFIG: Record<
  RiskLevel,
  { label: string; icon: typeof Shield; className: string }
> = {
  READ_ONLY: {
    label: "只读",
    icon: ShieldCheckIcon,
    className: "text-green-600 bg-green-50",
  },
  LOCAL_WRITE: {
    label: "可撤销",
    icon: Shield,
    className: "text-blue-600 bg-blue-50",
  },
  SENSITIVE: {
    label: "需确认",
    icon: ShieldAlert,
    className: "text-red-600 bg-red-50",
  },
};

function ActionCard({
  action,
  index,
  onConfirm,
}: {
  action: ActionPlanItem;
  index: number;
  onConfirm: (id: string) => void;
}) {
  const risk = RISK_CONFIG[action.risk_level];
  const RiskIcon = risk.icon;

  const isConfirmed = action.execution_status === "confirmed";
  const isDone = action.execution_status === "done";
  const isFailed = action.execution_status === "failed";

  return (
    <div
      className={`p-3 border rounded-lg transition-colors ${
        isFailed
          ? "border-red-200 bg-red-50"
          : isDone
            ? "border-green-200 bg-green-50"
            : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span className="shrink-0 w-5 h-5 flex items-center justify-center bg-gray-100 text-gray-500 text-[10px] font-semibold rounded-full mt-0.5">
          {index}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-900">
              {action.action_type}
            </span>
            {action.field_name && (
              <span className="text-xs text-gray-500">
                → {action.field_name}
              </span>
            )}
            <span
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${risk.className}`}
            >
              <RiskIcon className="w-3 h-3" aria-hidden="true" />
              {risk.label}
            </span>
          </div>

          {action.field_value && (
            <p className="text-xs text-gray-500 mt-1 truncate">
              值: {action.field_value}
              <span className="ml-2 text-gray-400">
                (来源: {action.value_source})
              </span>
            </p>
          )}

          {/* 状态与操作 */}
          <div className="mt-2 flex items-center gap-2">
            {isDone && (
              <span className="inline-flex items-center gap-1 text-xs text-green-700">
                <CheckCircle2 className="w-3 h-3" /> 已完成
              </span>
            )}
            {isFailed && (
              <span className="inline-flex items-center gap-1 text-xs text-red-700">
                <XCircle className="w-3 h-3" /> 执行失败
              </span>
            )}
            {isConfirmed && (
              <span className="inline-flex items-center gap-1 text-xs text-blue-700">
                <CheckCircle2 className="w-3 h-3" /> 已确认，等待执行
              </span>
            )}
            {action.requires_confirmation &&
              action.execution_status === "pending" && (
                <button
                  type="button"
                  onClick={() => onConfirm(action.action_id)}
                  className="text-xs font-medium text-red-700 bg-red-100 px-2.5 py-1 rounded
                    hover:bg-red-200 transition-colors"
                >
                  确认执行
                </button>
              )}
            {action.target_url && (
              <a
                href={action.target_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
              >
                <ExternalLink className="w-3 h-3" />
                目标页面
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ────────── 原文高亮 ────────── */

function renderHighlightedText(
  text: string,
  quote: string | null,
  isTrustworthy: boolean,
  ref: React.RefObject<HTMLSpanElement | null>
): React.ReactNode {
  if (!quote) return text;

  // 对引用做简单归一化匹配（对齐 text.py 的空格/换行归一化）
  const normalizedQuote = quote.replace(/\s+/g, " ").trim();
  const normalizedText = text.replace(/\s+/g, " ");
  const idx = normalizedText.toLowerCase().indexOf(normalizedQuote.toLowerCase());

  if (idx === -1) {
    // 定位失败 — 不伪造高亮位置
    return text;
  }

  // 映射回原文的位置（简化处理：按归一化后的字符索引切分）
  const before = text.substring(0, idx);
  const match = text.substring(idx, idx + normalizedQuote.length);
  const after = text.substring(idx + normalizedQuote.length);

  const highlightClass = isTrustworthy
    ? "bg-green-200 text-green-900 border-b-2 border-green-400"
    : "bg-red-200 text-red-900 border-b-2 border-red-400 line-through";

  return (
    <>
      {before}
      <span ref={ref as React.Ref<HTMLSpanElement>} className={`${highlightClass} px-0.5 rounded`}>
        {match}
      </span>
      {after}
    </>
  );
}
