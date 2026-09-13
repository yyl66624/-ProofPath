/**
 * 演示模式横幅
 *
 * 样例数据必须有可见标记，不与真实分析结果混淆（D-3 要求）。
 */
import { FlaskConical } from "lucide-react";

interface Props {
  visible: boolean;
}

export function DemoBanner({ visible }: Props) {
  if (!visible) return null;

  return (
    <div
      role="alert"
      className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 flex items-center gap-3"
    >
      <FlaskConical className="w-4 h-4 text-amber-600 shrink-0" aria-hidden="true" />
      <p className="text-sm text-amber-800">
        <span className="font-semibold">演示数据</span>
        <span className="mx-1.5">·</span>
        当前显示的是内置样例，不是真实分析结果。
        所有判断、引用和材料清单均来自预设数据。
      </p>
    </div>
  );
}
