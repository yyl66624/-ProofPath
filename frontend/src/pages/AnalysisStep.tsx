/**
 * 步骤3: 分析结果
 *
 * 展示条件判断、材料清单和证据核验摘要。
 * 分析中不伪造百分比（D-7）。
 * UNKNOWN 状态的结论明确标注证据核验未通过，不显示为已验证（D-5）。
 */
import { useState, useEffect, useCallback } from "react";
import {
  ArrowLeft,
  ArrowRight,
  RotateCcw,
  ClipboardList,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";
import { useApp } from "@/store/AppContext";
import { getAnalysisResult, retryAnalysis } from "@/api/client";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { CitationBadge } from "@/components/CitationBadge";
import type { ConditionVerdict, ApiError } from "@/types";

type PageState = "loading" | "ready" | "error" | "retrying";

export function AnalysisStep() {
  const { state, dispatch, goToStep, goBack } = useApp();
  const { analysisResult, document: doc } = state;

  const [pageState, setPageState] = useState<PageState>(
    analysisResult ? "ready" : "loading"
  );
  const [error, setError] = useState<string | null>(null);

  /* ── 加载分析结果 ── */
  const loadResult = useCallback(async () => {
    if (!doc) return;
    setPageState("loading");
    setError(null);

    try {
      const result = await getAnalysisResult(`task-${doc.doc_id}`);
      dispatch({ type: "SET_ANALYSIS_RESULT", result });
      setPageState("ready");
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.user_message || "获取分析结果失败");
      setPageState("error");
    }
  }, [doc, dispatch]);

  useEffect(() => {
    if (!analysisResult) {
      loadResult();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── 重试 ── */
  const handleRetry = useCallback(async () => {
    if (!doc) return;
    setPageState("retrying");
    setError(null);

    try {
      await retryAnalysis(`task-${doc.doc_id}`);
      await loadResult();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.user_message || "重试失败");
      setPageState("error");
    }
  }, [doc, loadResult]);

  /* ── 加载中 ── */
  if (pageState === "loading" || pageState === "retrying") {
    return (
      <LoadingSpinner
        message={
          pageState === "retrying" ? "正在重新分析…" : "正在分析政策文件…"
        }
      />
    );
  }

  /* ── 错误 ── */
  if (pageState === "error" || !analysisResult?.report) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <ErrorAlert
          title="分析失败"
          message={error || "未能获取分析结果"}
          canRetry
          onRetry={handleRetry}
          actions={[{ label: "返回修改资料", onClick: goBack }]}
        />
      </div>
    );
  }

  const { report, verification } = analysisResult;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* 摘要 */}
      {report.summary && (
        <div className="p-4 bg-brand-50 border border-brand-200 rounded-lg">
          <p className="text-sm text-brand-800">{report.summary}</p>
        </div>
      )}

      {/* 非终结性提示 */}
      {!isConclusive(report.verdicts) && (
        <div
          role="status"
          className="flex items-start gap-2.5 p-3 bg-gray-50 border border-gray-200 rounded-lg"
        >
          <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-xs text-gray-600">
            本结果不是最终资格认定，请以受理窗口的答复为准。
          </p>
        </div>
      )}

      {/* 逐条判定 */}
      <section aria-labelledby="verdicts-heading">
        <h3 id="verdicts-heading" className="text-lg font-semibold text-gray-900 mb-3">
          逐条判定
        </h3>
        <div className="space-y-3">
          {report.verdicts.map((v, idx) => (
            <VerdictCard key={idx} verdict={v} index={idx + 1} />
          ))}
        </div>
      </section>

      {/* 需要补充的信息 */}
      {report.verdicts.some((v) => v.missing_info.length > 0) && (
        <section
          aria-labelledby="missing-heading"
          className="p-4 bg-amber-50 border border-amber-200 rounded-lg"
        >
          <h3
            id="missing-heading"
            className="text-sm font-semibold text-amber-800 mb-2"
          >
            还需要你确认
          </h3>
          <ul className="space-y-1">
            {report.verdicts.flatMap((v) =>
              v.missing_info.map((info, i) => (
                <li key={`${v.condition}-${i}`} className="text-sm text-amber-700 flex items-start gap-2">
                  <span className="text-amber-500 mt-0.5">•</span>
                  {info}
                </li>
              ))
            )}
          </ul>
        </section>
      )}

      {/* 材料清单 */}
      <section aria-labelledby="checklist-heading">
        <h3
          id="checklist-heading"
          className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2"
        >
          <ClipboardList className="w-5 h-5 text-brand-600" aria-hidden="true" />
          材料清单
        </h3>
        <ul className="space-y-2">
          {report.checklist.map((item, idx) => (
            <li
              key={idx}
              className="flex items-start gap-3 p-3 bg-white border border-gray-200 rounded-lg"
            >
              <span className="shrink-0 w-6 h-6 flex items-center justify-center bg-brand-50 text-brand-700 text-xs font-semibold rounded-full">
                {idx + 1}
              </span>
              <span className="text-sm text-gray-700">{item}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* 证据核验摘要 */}
      {verification && (
        <section
          aria-labelledby="verification-heading"
          className="p-4 bg-white border border-gray-200 rounded-lg"
        >
          <h3
            id="verification-heading"
            className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2"
          >
            <ShieldCheck className="w-4 h-4 text-brand-600" aria-hidden="true" />
            证据核验
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div>
              <div className="text-2xl font-bold text-gray-900">
                {verification.total_citations}
              </div>
              <div className="text-xs text-gray-500">引用总数</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-green-600">
                {verification.verified}
              </div>
              <div className="text-xs text-gray-500">已核验</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-blue-600">
                {verification.partial}
              </div>
              <div className="text-xs text-gray-500">基本一致</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-red-600">
                {verification.rejected}
              </div>
              <div className="text-xs text-gray-500">未通过</div>
            </div>
          </div>
          {verification.downgraded_conditions > 0 && (
            <p className="mt-3 text-xs text-gray-600 border-t pt-2">
              有 {verification.downgraded_conditions} 条结论因引用无法核验，已降级为"原文未明确"。
            </p>
          )}
        </section>
      )}

      {/* 操作按钮 */}
      <div className="flex items-center justify-between gap-4 pt-2">
        <button
          type="button"
          onClick={goBack}
          className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium
            text-gray-700 bg-white border border-gray-300 rounded-lg
            hover:bg-gray-50 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" />
          修改资料
        </button>

        <div className="flex gap-2">
          {analysisResult.task.can_retry && (
            <button
              type="button"
              onClick={handleRetry}
              className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium
                text-gray-700 bg-white border border-gray-300 rounded-lg
                hover:bg-gray-50 transition-colors"
            >
              <RotateCcw className="w-4 h-4" aria-hidden="true" />
              重新分析
            </button>
          )}
          <button
            type="button"
            onClick={() => goToStep("evidence")}
            className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium
              text-white bg-brand-600 rounded-lg
              hover:bg-brand-700 transition-colors"
          >
            查看原文与证据
            <ArrowRight className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ────────── 单条判定卡片 ────────── */

function VerdictCard({
  verdict,
  index,
}: {
  verdict: ConditionVerdict;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-gray-50 transition-colors"
      >
        <span className="shrink-0 w-6 h-6 flex items-center justify-center bg-gray-100 text-gray-600 text-xs font-semibold rounded-full">
          {index}
        </span>
        <span className="flex-1 text-sm text-gray-900">{verdict.condition}</span>
        <StatusBadge status={verdict.status} />
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100 pt-3">
          {/* 理由 */}
          <div className="text-sm text-gray-600 whitespace-pre-line">
            {verdict.rationale}
          </div>

          {/* 引用 */}
          {verdict.citations.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-500">引用证据</p>
              {verdict.citations.map((vc, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2 p-2.5 rounded-md text-sm
                    ${vc.status === "VERIFIED" || vc.status === "PARTIAL"
                      ? "bg-green-50 border border-green-100"
                      : "bg-red-50 border border-red-100"
                    }`}
                >
                  <CitationBadge status={vc.status} coverage={vc.coverage} />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs text-gray-500">
                      第 {vc.citation.page} 页
                    </span>
                    <p className="text-sm text-gray-700 mt-0.5">
                      "{vc.citation.quote}"
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 缺失信息 */}
          {verdict.missing_info.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-amber-600">需要补充</p>
              {verdict.missing_info.map((info, i) => (
                <p key={i} className="text-sm text-amber-700">
                  • {info}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ────────── 辅助 ────────── */

function isConclusive(verdicts: ConditionVerdict[]): boolean {
  return (
    verdicts.length > 0 &&
    verdicts.every((v) => v.status === "MET" || v.status === "UNMET")
  );
}
