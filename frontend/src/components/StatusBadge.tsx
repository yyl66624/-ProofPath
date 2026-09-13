/**
 * 条件判断状态徽章
 *
 * 同时使用颜色、图标和文字标签来传达状态，
 * 不只依赖红绿颜色区分（满足 D-6 要求）。
 */
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";
import type { ConditionStatus } from "@/types";

const STATUS_CONFIG: Record<
  ConditionStatus,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  MET: {
    label: "满足",
    icon: CheckCircle2,
    className: "badge--met",
  },
  UNMET: {
    label: "不满足",
    icon: XCircle,
    className: "badge--unmet",
  },
  NEEDS_INPUT: {
    label: "待补充",
    icon: AlertTriangle,
    className: "badge--needs-input",
  },
  UNKNOWN: {
    label: "原文未明确",
    icon: HelpCircle,
    className: "badge--unknown",
  },
};

interface Props {
  status: ConditionStatus;
  size?: "sm" | "md";
}

export function StatusBadge({ status, size = "md" }: Props) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <span
      className={`badge ${config.className} ${size === "sm" ? "text-[10px] px-2 py-0.5" : ""}`}
      role="status"
      aria-label={`条件状态：${config.label}`}
    >
      <Icon
        className={size === "sm" ? "w-3 h-3" : "w-3.5 h-3.5"}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}
