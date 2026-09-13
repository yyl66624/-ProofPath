/**
 * 加载指示器
 *
 * 不伪造完成百分比，只展示真实状态（D-7 要求）。
 */
import { Loader2 } from "lucide-react";

interface Props {
  /** 当前阶段的描述，如"正在解析文档…" */
  message?: string;
  /** 是否全屏覆盖 */
  overlay?: boolean;
}

export function LoadingSpinner({ message, overlay }: Props) {
  const content = (
    <div className="flex flex-col items-center gap-3" role="status">
      <Loader2
        className="w-8 h-8 text-brand-600 animate-spin"
        aria-hidden="true"
      />
      {message && (
        <p className="text-sm text-gray-600 animate-pulse">{message}</p>
      )}
      <span className="sr-only">正在加载</span>
    </div>
  );

  if (overlay) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 backdrop-blur-sm">
        {content}
      </div>
    );
  }

  return <div className="flex justify-center py-12">{content}</div>;
}
