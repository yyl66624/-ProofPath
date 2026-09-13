/**
 * 步骤指示器 — 显示四步流程的当前进度
 *
 * 可访问性：使用 aria-current 标记当前步骤，
 * 已完成步骤使用 aria-label 说明状态。
 */
import {
  FileUp,
  UserRoundPen,
  SearchCheck,
  FileText,
  Check,
} from "lucide-react";
import type { WizardStep } from "@/types";

const STEPS: { key: WizardStep; label: string; icon: typeof FileUp }[] = [
  { key: "upload", label: "上传文件", icon: FileUp },
  { key: "profile", label: "补充资料", icon: UserRoundPen },
  { key: "analysis", label: "分析结果", icon: SearchCheck },
  { key: "evidence", label: "原文与行动", icon: FileText },
];

const STEP_ORDER: WizardStep[] = ["upload", "profile", "analysis", "evidence"];

interface Props {
  current: WizardStep;
  onStepClick?: (step: WizardStep) => void;
}

export function StepIndicator({ current, onStepClick }: Props) {
  const currentIdx = STEP_ORDER.indexOf(current);

  return (
    <nav aria-label="流程步骤" className="w-full">
      <ol className="flex items-center justify-between gap-2 sm:gap-4">
        {STEPS.map((step, idx) => {
          const isCompleted = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          const isPending = idx > currentIdx;
          const Icon = isCompleted ? Check : step.icon;

          const canClick = isCompleted && onStepClick;

          return (
            <li key={step.key} className="flex-1 flex flex-col items-center gap-2">
              {/* 连接线 + 圆圈 */}
              <div className="flex items-center w-full">
                {idx > 0 && (
                  <div
                    className={`flex-1 h-0.5 ${
                      idx <= currentIdx ? "bg-brand-500" : "bg-gray-200"
                    }`}
                    aria-hidden="true"
                  />
                )}
                <button
                  type="button"
                  onClick={() => canClick && onStepClick(step.key)}
                  disabled={!canClick}
                  aria-current={isCurrent ? "step" : undefined}
                  aria-label={
                    isCompleted
                      ? `${step.label}（已完成）`
                      : isCurrent
                        ? `${step.label}（当前步骤）`
                        : `${step.label}（未开始）`
                  }
                  className={`
                    step-indicator shrink-0 transition-colors
                    ${isCurrent ? "step-indicator--active" : ""}
                    ${isCompleted ? "step-indicator--completed cursor-pointer hover:bg-brand-200" : ""}
                    ${isPending ? "step-indicator--pending" : ""}
                    ${!canClick ? "cursor-default" : ""}
                  `}
                >
                  <Icon className="w-4 h-4" aria-hidden="true" />
                </button>
                {idx < STEPS.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 ${
                      idx < currentIdx ? "bg-brand-500" : "bg-gray-200"
                    }`}
                    aria-hidden="true"
                  />
                )}
              </div>
              {/* 标签 */}
              <span
                className={`text-xs font-medium text-center ${
                  isCurrent
                    ? "text-brand-700"
                    : isCompleted
                      ? "text-brand-600"
                      : "text-gray-400"
                }`}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
