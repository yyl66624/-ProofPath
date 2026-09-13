/**
 * 步骤2: 资料补充
 *
 * 仅询问与条件相关的字段（由 missing_info 驱动）。
 * 保留已填写内容，失败后不清空输入。
 */
import { useState, useCallback } from "react";
import { ArrowLeft, ArrowRight, Ban } from "lucide-react";
import { useApp } from "@/store/AppContext";
import { submitProfile, startAnalysis } from "@/api/client";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";
import type { ApiError } from "@/types";

type SubmitState = "idle" | "submitting" | "error";

export function ProfileStep() {
  const { state, dispatch, goToStep, goBack, canGoBack } = useApp();
  const { profileFields, profileValues, document: doc, question } = state;

  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);

  /* ── 更新字段值 ── */
  const handleChange = useCallback(
    (fieldName: string, value: string) => {
      dispatch({ type: "UPDATE_PROFILE_VALUE", fieldName, value });
    },
    [dispatch]
  );

  /* ── 标记不愿提供 ── */
  const handleDecline = useCallback(
    (fieldName: string) => {
      dispatch({ type: "UPDATE_PROFILE_VALUE", fieldName, value: "__DECLINED__" });
    },
    [dispatch]
  );

  /* ── 提交 ── */
  const handleSubmit = useCallback(async () => {
    if (!doc) return;
    setSubmitState("submitting");
    setError(null);

    try {
      // 提交资料校验
      const result = await submitProfile(doc.doc_id, profileValues);
      if (!result.accepted && result.errors) {
        dispatch({ type: "SET_PROFILE_ERRORS", errors: result.errors });
        setSubmitState("idle");
        return;
      }

      // 发起分析
      await startAnalysis(doc.doc_id, question, profileValues);
      goToStep("analysis");
    } catch (err) {
      setSubmitState("error");
      const apiErr = err as ApiError;
      setError(apiErr.user_message || "提交失败，请稍后重试");
    }
  }, [doc, question, profileValues, dispatch, goToStep]);

  if (submitState === "submitting") {
    return <LoadingSpinner message="正在提交资料…" />;
  }

  const hasRequiredEmpty = profileFields.some(
    (f) => f.required && !profileValues[f.field_name] && profileValues[f.field_name] !== "__DECLINED__"
  );

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 标题 */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900">
          补充个人资料
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          以下信息用于判断你是否符合条件。如果不愿提供某项，系统会标记为"待补充"，
          对应条件无法做出判断。
        </p>
      </div>

      {/* 表单字段 */}
      <div className="space-y-4">
        {profileFields.map((field) => {
          const value = profileValues[field.field_name] || "";
          const isDeclined = value === "__DECLINED__";
          const hasError = !!field.error;

          return (
            <div key={field.field_name}>
              <div className="flex items-center justify-between mb-1.5">
                <label
                  htmlFor={`field-${field.field_name}`}
                  className="block text-sm font-medium text-gray-700"
                >
                  {field.label}
                  {field.required && (
                    <span className="text-red-500 ml-0.5" aria-label="必填">*</span>
                  )}
                </label>
                {!field.required && (
                  <button
                    type="button"
                    onClick={() => handleDecline(field.field_name)}
                    className="text-xs text-gray-400 hover:text-gray-600 inline-flex items-center gap-1"
                    aria-label={`不愿提供${field.label}`}
                  >
                    <Ban className="w-3 h-3" />
                    不愿提供
                  </button>
                )}
              </div>

              {isDeclined ? (
                <div className="px-3 py-2 text-sm text-gray-400 bg-gray-50 border border-gray-200 rounded-lg italic">
                  已标记为不提供
                  <button
                    type="button"
                    onClick={() => handleChange(field.field_name, "")}
                    className="ml-2 text-brand-600 hover:underline not-italic"
                  >
                    撤销
                  </button>
                </div>
              ) : (
                <input
                  id={`field-${field.field_name}`}
                  type="text"
                  value={value}
                  onChange={(e) => handleChange(field.field_name, e.target.value)}
                  placeholder={field.value || `请输入${field.label}`}
                  aria-invalid={hasError}
                  aria-describedby={hasError ? `error-${field.field_name}` : undefined}
                  className={`
                    w-full px-3 py-2 text-sm border rounded-lg transition-colors
                    placeholder:text-gray-400
                    ${hasError
                      ? "border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-500"
                      : "border-gray-300 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                    }
                  `}
                />
              )}

              {hasError && (
                <p
                  id={`error-${field.field_name}`}
                  className="mt-1 text-xs text-red-600"
                  role="alert"
                >
                  {field.error}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* 错误 */}
      {error && (
        <ErrorAlert
          message={error}
          canRetry
          onRetry={handleSubmit}
        />
      )}

      {/* 操作按钮 */}
      <div className="flex items-center justify-between gap-4 pt-2">
        <button
          type="button"
          onClick={goBack}
          disabled={!canGoBack}
          className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium
            text-gray-700 bg-white border border-gray-300 rounded-lg
            hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" />
          返回上传
        </button>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={hasRequiredEmpty}
          className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium
            text-white bg-brand-600 rounded-lg
            hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          提交并分析
          <ArrowRight className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
