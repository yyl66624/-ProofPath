/**
 * 错误提示组件
 *
 * 错误提示应指出用户能够采取的动作（0号文件 §8）。
 */
import { AlertCircle, RotateCcw } from "lucide-react";

interface Props {
  title?: string;
  message: string;
  canRetry?: boolean;
  onRetry?: () => void;
  /** 额外的用户可执行动作 */
  actions?: { label: string; onClick: () => void }[];
}

export function ErrorAlert({
  title = "出错了",
  message,
  canRetry,
  onRetry,
  actions,
}: Props) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4"
    >
      <div className="flex gap-3">
        <AlertCircle
          className="w-5 h-5 text-red-600 shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-red-800">{title}</h3>
          <p className="mt-1 text-sm text-red-700">{message}</p>

          {(canRetry || actions?.length) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {canRetry && onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
                    text-red-700 bg-red-100 rounded-md hover:bg-red-200
                    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600
                    transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                  重试
                </button>
              )}
              {actions?.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={action.onClick}
                  className="inline-flex items-center px-3 py-1.5 text-xs font-medium
                    text-gray-700 bg-white border border-gray-300 rounded-md
                    hover:bg-gray-50 transition-colors"
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
