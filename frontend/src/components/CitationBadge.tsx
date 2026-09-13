/**
 * 引用核验状态徽章
 *
 * 核验未通过的引用绝不显示为已验证（D-5 要求）。
 */
import {
  CheckCircle2,
  AlertCircle,
  XCircle,
  AlertTriangle,
  FileQuestion,
} from "lucide-react";
import type { CitationStatus } from "@/types";

const CITATION_CONFIG: Record<
  CitationStatus,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  VERIFIED: {
    label: "已核验",
    icon: CheckCircle2,
    className: "citation-badge--verified",
  },
  PARTIAL: {
    label: "基本一致",
    icon: AlertCircle,
    className: "citation-badge--partial",
  },
  NOT_FOUND: {
    label: "未能定位",
    icon: XCircle,
    className: "citation-badge--not-found",
  },
  TOO_SHORT: {
    label: "引用过短",
    icon: AlertTriangle,
    className: "citation-badge--too-short",
  },
  BAD_PAGE: {
    label: "页码不存在",
    icon: FileQuestion,
    className: "citation-badge--bad-page",
  },
};

interface Props {
  status: CitationStatus;
  coverage?: number;
}

export function CitationBadge({ status, coverage }: Props) {
  const config = CITATION_CONFIG[status];
  const Icon = config.icon;

  return (
    <span
      className={`badge ${config.className}`}
      role="status"
      aria-label={`引用状态：${config.label}${coverage !== undefined && status !== "VERIFIED" ? `（匹配度 ${Math.round(coverage * 100)}%）` : ""}`}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      {config.label}
      {coverage !== undefined && status !== "VERIFIED" && (
        <span className="text-[10px] opacity-75">
          {Math.round(coverage * 100)}%
        </span>
      )}
    </span>
  );
}
