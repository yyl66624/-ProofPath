/**
 * 样例数据 — 基于 demo.py 中的演示场景
 *
 * ⚠️ 样例模式标记：所有来自此文件的数据在 UI 上必须显示
 *    「演示数据」横幅，不得与真实分析结果混淆。
 */
import type {
  DocumentInfo,
  UserProfileField,
  ConditionVerdict,
  VerificationSummary,
  EligibilityReport,
  AnalysisTask,
  AnalysisResult,
  ActionPlanItem,
} from "@/types";

/* ────────── 文档 ────────── */

export const MOCK_DOCUMENT: DocumentInfo = {
  doc_id: "doc-demo-001",
  filename: "市人才安居租房补贴实施细则(试行).txt",
  format: "text/plain",
  status: "ready",
  page_count: 2,
};

/* ────────── 用户问题 ────────── */

export const MOCK_QUESTION =
  "我硕士毕业,28岁,在本市工作了8个月,社保交了8个月,名下没有房,已经网签备案了租房合同。我能申请多少补贴?需要准备什么?";

/* ────────── 用户资料 ────────── */

export const MOCK_PROFILE_FIELDS: UserProfileField[] = [
  { field_name: "education", label: "学历", value: "硕士研究生", source: "user_input", required: true },
  { field_name: "age", label: "年龄", value: "28岁", source: "user_input", required: true },
  { field_name: "social_insurance", label: "社保缴纳", value: "本市连续8个月", source: "user_input", required: true },
  { field_name: "own_housing", label: "自有住房", value: "无", source: "user_input", required: true },
  { field_name: "rental_filing", label: "租赁备案", value: "已完成网签备案", source: "user_input", required: true },
  { field_name: "rental_filing_date", label: "租赁合同网签备案日期", value: "", source: "not_provided", required: true, error: "请填写备案日期，用于判断是否在申请时限内" },
];

/* ────────── 分析报告 ────────── */

export const MOCK_VERDICTS: ConditionVerdict[] = [
  {
    condition: "学历要求：全日制本科及以上学历，或中级及以上职称",
    status: "MET",
    rationale: "你是硕士研究生，符合本科及以上的学历要求。",
    citations: [
      {
        citation: { page: 1, quote: "具有全日制本科及以上学历,或具有中级及以上专业技术职称" },
        status: "VERIFIED",
        coverage: 1.0,
      },
    ],
    missing_info: [],
  },
  {
    condition: "年龄要求：申请时不超过35周岁",
    status: "MET",
    rationale: "你28岁，在35周岁上限之内。",
    citations: [
      {
        citation: { page: 1, quote: "申请时年龄不超过35周岁" },
        status: "VERIFIED",
        coverage: 1.0,
      },
    ],
    missing_info: [],
  },
  {
    condition: "社保要求：在本市连续缴纳社会保险满6个月",
    status: "MET",
    rationale: "你已连续缴纳8个月，超过6个月的下限。",
    citations: [
      {
        citation: { page: 1, quote: "在本市连续缴纳\n社会保险满6个月" },
        status: "VERIFIED",
        coverage: 1.0,
      },
    ],
    missing_info: [],
  },
  {
    condition: "补贴标准：硕士研究生每月1500元，且首次申请可追补3个月",
    status: "UNKNOWN",
    rationale:
      "按学历分档，硕士对应每月1500元，并可追补此前3个月。\n[证据核验未通过] 引用“首次申请的人员可以追补此前3个月的补贴”未在原文中找到",
    citations: [
      {
        citation: { page: 2, quote: "硕士研究生或副高级职称,每月1500元" },
        status: "VERIFIED",
        coverage: 1.0,
      },
      {
        citation: { page: 2, quote: "首次申请的人员可以追补此前3个月的补贴" },
        status: "NOT_FOUND",
        coverage: 0.11,
      },
    ],
    missing_info: [],
  },
  {
    condition: "劳动合同期限不少于1年",
    status: "UNKNOWN",
    rationale:
      "你与本市用人单位已建立劳动关系。\n[证据核验未通过] 引用“合同”过短，不足为证",
    citations: [
      {
        citation: { page: 1, quote: "合同" },
        status: "TOO_SHORT",
        coverage: 0.0,
      },
    ],
    missing_info: [],
  },
  {
    condition: "申请时限：租赁合同备案之日起6个月内提出申请",
    status: "NEEDS_INPUT",
    rationale: "原文对申请时限有硬性要求，但你没有说明备案的具体日期。",
    citations: [
      {
        citation: { page: 2, quote: "申请人应当在租赁合同备案之日起6个月内提出申请,逾期不再受理" },
        status: "VERIFIED",
        coverage: 1.0,
      },
    ],
    missing_info: ["住房租赁合同网签备案的具体日期"],
  },
];

export const MOCK_CHECKLIST: string[] = [
  "租房补贴申请表（在线填写并打印签字）",
  "身份证正反面复印件",
  "硕士学历学位证书（国外学历需教育部留学服务中心认证书）",
  "劳动合同复印件",
  "近6个月社会保险缴纳记录",
  "住房租赁合同网签备案证明",
  "本人名下本市银行账户信息",
];

export const MOCK_REPORT: EligibilityReport = {
  doc_id: "doc-demo-001",
  question: MOCK_QUESTION,
  verdicts: MOCK_VERDICTS,
  checklist: MOCK_CHECKLIST,
  summary:
    "按你提供的信息，补贴标准对应每月1500元，主要条件均已满足，另有一项申请时限需要你补充确认。",
};

export const MOCK_VERIFICATION: VerificationSummary = {
  total_citations: 7,
  verified: 5,
  partial: 0,
  rejected: 2,
  downgraded_conditions: 2,
};

export const MOCK_TASK: AnalysisTask = {
  task_id: "task-demo-001",
  doc_id: "doc-demo-001",
  status: "success",
  current_stage: "完成",
  updated_at: new Date().toISOString(),
  can_retry: false,
};

export const MOCK_ANALYSIS_RESULT: AnalysisResult = {
  task: MOCK_TASK,
  report: MOCK_REPORT,
  verification: MOCK_VERIFICATION,
};

/* ────────── 操作计划（P10 受控填表） ────────── */

export const MOCK_ACTION_PLAN: ActionPlanItem[] = [
  {
    action_id: "act-001",
    target_url: "https://example.gov.cn/apply",
    action_type: "navigate",
    field_name: "",
    field_value: "https://example.gov.cn/apply",
    value_source: "系统",
    risk_level: "READ_ONLY",
    execution_status: "pending",
    requires_confirmation: false,
  },
  {
    action_id: "act-002",
    target_url: "https://example.gov.cn/apply",
    action_type: "fill",
    field_name: "申请人姓名",
    field_value: "",
    value_source: "用户输入",
    risk_level: "LOCAL_WRITE",
    execution_status: "pending",
    requires_confirmation: false,
  },
  {
    action_id: "act-003",
    target_url: "https://example.gov.cn/apply",
    action_type: "upload",
    field_name: "学历学位证书",
    field_value: "",
    value_source: "用户上传",
    risk_level: "SENSITIVE",
    execution_status: "pending",
    requires_confirmation: true,
  },
  {
    action_id: "act-004",
    target_url: "https://example.gov.cn/apply",
    action_type: "submit",
    field_name: "提交申请",
    field_value: "",
    value_source: "系统",
    risk_level: "SENSITIVE",
    execution_status: "pending",
    requires_confirmation: true,
  },
];

/* ────────── 原文页面文本（用于证据定位高亮） ────────── */

export const MOCK_PAGE_TEXTS: Record<number, string> = {
  1: `市人才安居租房补贴实施细则(试行)

第一章 总则

第一条 为吸引和留住各类人才,支持在本市稳定就业的青年人才解决阶段性住房困难,制定本细则。

第二条 本细则所称租房补贴,是指对符合条件的申请人,按月发放的租金补助资金。

第二章 申请条件

第三条 申请人应当同时符合以下条件:

(一)具有全日制本科及以上学历,或具有中级及以上专业技术职称;

(二)申请时年龄不超过35周岁,其中具有博士学位的不超过40周岁;

(三)与本市用人单位签订劳动合同且期限不少于1年,并在本市连续缴纳社会保险满6个月;

(四)本人及配偶在本市均无自有产权住房,且未享受公租房、人才公寓等其他住房保障政策;

(五)在本市租赁住房并已办理住房租赁合同网签备案。

第四条 申请人有下列情形之一的,不予受理:

(一)提供虚假材料骗取补贴的;

(二)已在其他区县享受同类租房补贴的。`,

  2: `第三章 补贴标准

第五条 补贴标准按学历和职称分档确定:

(一)博士研究生或正高级职称,每月2000元;

(二)硕士研究生或副高级职称,每月1500元;

(三)全日制本科或中级职称,每月1000元。

第六条 补贴发放期限最长不超过36个月,期满后不再续发。

第四章 申请材料

第七条 申请人应当提交以下材料:

(一)租房补贴申请表(在线填写并打印签字);

(二)本人身份证正反面复印件;

(三)学历学位证书,国外学历需提供教育部留学服务中心认证书;

(四)与用人单位签订的劳动合同复印件;

(五)近6个月社会保险缴纳记录(可在市社保局官网自行下载);

(六)住房租赁合同网签备案证明;

(七)本人名下本市银行账户信息。

第五章 办理流程

第八条 办理流程如下:

(一)申请人通过市人才服务平台在线提交申请;

(二)用人单位在5个工作日内完成在线核实;

(三)区人才服务中心在10个工作日内完成初审;

(四)市人才服务中心在10个工作日内完成复核并公示5个工作日;

(五)公示无异议后,自次月起按月发放补贴。

第九条 申请人应当在租赁合同备案之日起6个月内提出申请,逾期不再受理。`,
};
