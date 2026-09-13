/**
 * 步骤1: 文件与问题输入
 *
 * 支持拖拽上传、演示样例快捷入口。
 * 上传状态：初始 → 上传中 → 完成/失败/不支持格式
 */
import { useState, useRef, useCallback } from "react";
import { FileUp, FlaskConical, FileText, X } from "lucide-react";
import { useApp } from "@/store/AppContext";
import { uploadDocument, getProfileFields, setDemoMode } from "@/api/client";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ErrorAlert } from "@/components/ErrorAlert";
import { MOCK_DOCUMENT, MOCK_QUESTION, MOCK_PROFILE_FIELDS } from "@/mock/data";
import type { ApiError } from "@/types";

/** 允许的文件类型 — 待 C 确认实际支持的格式 */
const ACCEPTED_TYPES = [".txt", ".pdf"];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB，待 C 确认

type UploadState = "idle" | "uploading" | "error";

export function UploadStep() {
  const { dispatch, goToStep } = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  /* ── 文件校验 ── */
  const validateFile = useCallback((file: File): string | null => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED_TYPES.includes(ext)) {
      return `不支持的文件格式（${ext}）。目前支持：${ACCEPTED_TYPES.join("、")}`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `文件过大（${(file.size / 1024 / 1024).toFixed(1)}MB）。上限 ${MAX_FILE_SIZE / 1024 / 1024}MB`;
    }
    if (file.size === 0) {
      return "文件为空，请选择有效文件";
    }
    return null;
  }, []);

  /* ── 选择文件 ── */
  const handleFileSelect = useCallback(
    (file: File) => {
      setError(null);
      const err = validateFile(file);
      if (err) {
        setError(err);
        setSelectedFile(null);
        return;
      }
      setSelectedFile(file);
    },
    [validateFile]
  );

  /* ── 拖拽 ── */
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect]
  );

  /* ── 上传 ── */
  const handleUpload = useCallback(async () => {
    if (!selectedFile || !question.trim()) return;
    setUploadState("uploading");
    setError(null);

    try {
      const doc = await uploadDocument(selectedFile, question.trim());
      dispatch({ type: "SET_DOCUMENT", document: doc, question: question.trim() });

      const fields = await getProfileFields(doc.doc_id);
      dispatch({ type: "SET_PROFILE_FIELDS", fields });
      goToStep("profile");
    } catch (err) {
      setUploadState("error");
      const apiErr = err as ApiError;
      setError(apiErr.user_message || "上传失败，请稍后重试");
    }
  }, [selectedFile, question, dispatch, goToStep]);

  /* ── 演示模式快速开始 ── */
  const handleDemoStart = useCallback(() => {
    setDemoMode(true);
    dispatch({ type: "SET_DEMO_MODE", enabled: true });
    dispatch({
      type: "SET_DOCUMENT",
      document: MOCK_DOCUMENT,
      question: MOCK_QUESTION,
    });
    dispatch({ type: "SET_PROFILE_FIELDS", fields: MOCK_PROFILE_FIELDS });
    goToStep("profile");
  }, [dispatch, goToStep]);

  /* ── 清除文件 ── */
  const handleClearFile = useCallback(() => {
    setSelectedFile(null);
    setError(null);
    setUploadState("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  if (uploadState === "uploading") {
    return <LoadingSpinner message="正在上传并解析文件…" />;
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 标题 */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900">
          上传政策文件
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          上传需要核验的政策 PDF 或文本文件，并输入你的问题。
        </p>
      </div>

      {/* 拖拽上传区 */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`
          relative border-2 border-dashed rounded-xl p-8 text-center transition-colors
          ${dragOver ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-gray-400"}
          ${selectedFile ? "bg-gray-50" : ""}
        `}
      >
        {selectedFile ? (
          /* 已选择文件 */
          <div className="flex items-center justify-center gap-3">
            <FileText className="w-8 h-8 text-brand-600" aria-hidden="true" />
            <div className="text-left">
              <p className="text-sm font-medium text-gray-900">
                {selectedFile.name}
              </p>
              <p className="text-xs text-gray-500">
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={handleClearFile}
              className="ml-4 p-1 rounded-full hover:bg-gray-200 transition-colors"
              aria-label="移除文件"
            >
              <X className="w-4 h-4 text-gray-500" />
            </button>
          </div>
        ) : (
          /* 未选择 */
          <div className="space-y-3">
            <FileUp
              className="w-10 h-10 mx-auto text-gray-400"
              aria-hidden="true"
            />
            <div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="text-sm font-medium text-brand-600 hover:text-brand-700"
              >
                选择文件
              </button>
              <span className="text-sm text-gray-500"> 或拖拽到此处</span>
            </div>
            <p className="text-xs text-gray-400">
              支持 {ACCEPTED_TYPES.join("、")}，最大 {MAX_FILE_SIZE / 1024 / 1024}MB
            </p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelect(file);
          }}
          className="hidden"
          aria-label="选择要上传的文件"
        />
      </div>

      {/* 问题输入 */}
      <div>
        <label
          htmlFor="question-input"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          你的问题
        </label>
        <textarea
          id="question-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="例：我硕士毕业28岁，社保交了8个月，能申请多少补贴？需要准备什么？"
          rows={3}
          className="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg
            placeholder:text-gray-400 focus:border-brand-500 focus:ring-1 focus:ring-brand-500
            resize-none transition-colors"
        />
      </div>

      {/* 错误 */}
      {error && (
        <ErrorAlert
          message={error}
          canRetry={uploadState === "error"}
          onRetry={handleUpload}
        />
      )}

      {/* 操作按钮 */}
      <div className="flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={handleDemoStart}
          className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium
            text-amber-700 bg-amber-50 border border-amber-200 rounded-lg
            hover:bg-amber-100 transition-colors"
        >
          <FlaskConical className="w-4 h-4" aria-hidden="true" />
          使用演示样例
        </button>

        <button
          type="button"
          onClick={handleUpload}
          disabled={!selectedFile || !question.trim()}
          className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium
            text-white bg-brand-600 rounded-lg
            hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors"
        >
          <FileUp className="w-4 h-4" aria-hidden="true" />
          上传并继续
        </button>
      </div>
    </div>
  );
}
