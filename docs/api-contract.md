# ProofPath 接口契约（前端需求版）

> 提交人：D（前端负责人）→ 审阅人：C（后端负责人）
>
> 版本：draft-0.1 ｜ 日期：2026-09-13
>
> 依据：00-团队项目0号文档 第七章 7.3 联调前必须约定的数据；后端 `models.py`、`errors.py`、`actions.py`、`verifier.py`、`demo.py` 现有实现。

---

## 一、接口总览

| # | 方法 | 路径 | 说明 | 对应页面步骤 |
|---|------|------|------|-------------|
| 1 | `POST` | `/api/documents` | 上传政策文件 | 步骤 1：文件与问题输入 |
| 2 | `GET` | `/api/documents/{doc_id}` | 查询文档详情与处理状态 | 步骤 1 |
| 3 | `GET` | `/api/documents/{doc_id}/chunks` | 获取文档原文片段列表 | 步骤 4：原文与行动 |
| 4 | `POST` | `/api/analyses` | 提交分析任务（含问题和资料） | 步骤 1 → 步骤 2 |
| 5 | `GET` | `/api/analyses/{analysis_id}` | 查询分析任务状态与结果 | 步骤 2 / 步骤 3 |
| 6 | `PATCH` | `/api/analyses/{analysis_id}/profile` | 补充或修改用户资料 | 步骤 2：资料补充 |
| 7 | `POST` | `/api/analyses/{analysis_id}/rerun` | 补充资料后重新分析 | 步骤 2 → 步骤 3 |
| 8 | `GET` | `/api/analyses/{analysis_id}/report` | 获取完整分析报告 | 步骤 3：分析结果 |
| 9 | `GET` | `/api/analyses/{analysis_id}/citations/{verdict_index}` | 获取单条判定的引用原文上下文 | 步骤 4：原文与行动 |
| 10 | `GET` | `/api/analyses/{analysis_id}/plan` | 获取操作计划（表单预填方案） | 步骤 4：原文与行动 |
| 11 | `POST` | `/api/analyses/{analysis_id}/plan/confirm` | 确认敏感操作 | 步骤 4：原文与行动 |

---

## 二、数据对象 JSON Schema

### 2.1 Document（文档）

对齐 `models.Document`，补充 0 号文件要求的名称、格式、处理状态、版本摘要。

```json
{
  "type": "object",
  "required": ["doc_id", "name", "format", "status", "parser", "page_count", "chunk_count", "content_hash"],
  "additionalProperties": false,
  "properties": {
    "doc_id":       { "type": "string", "description": "内容寻址标识，来自 sha256 前 16 位 + 文件名" },
    "name":         { "type": "string", "description": "原始文件名" },
    "format":       { "type": "string", "enum": ["pdf", "txt", "md", "docx", "pptx", "xlsx", "html", "png", "jpg", "jpeg"], "description": "文件格式（小写后缀）" },
    "status":       { "$ref": "#/$defs/DocumentStatus" },
    "parser":       { "type": "string", "enum": ["pypdf", "plaintext", "docling"], "description": "实际使用的解析器" },
    "page_count":   { "type": "integer", "minimum": 0 },
    "chunk_count":  { "type": "integer", "minimum": 0 },
    "content_hash": { "type": "string", "description": "文件内容 sha256 前 16 位，用作版本标识" },
    "error":        { "type": ["string", "null"], "description": "解析失败时的错误说明" },
    "created_at":   { "type": "string", "format": "date-time" }
  }
}
```

### 2.2 Chunk（原文片段）

对齐 `models.Chunk`，补充所属文档。非 PDF 不伪造页码：纯文本以 `--- PAGE BREAK ---` 分页时 page 为分段序号，无分页标记则 page=1。

```json
{
  "type": "object",
  "required": ["chunk_id", "doc_id", "page", "text"],
  "additionalProperties": false,
  "properties": {
    "chunk_id": { "type": "string", "description": "片段标识，格式 {doc_prefix}-p{page}-c{index}" },
    "doc_id":   { "type": "string", "description": "所属文档标识" },
    "page":     { "type": "integer", "minimum": 1, "description": "所属页码（1-indexed）；纯文本按分页标记分段，无标记则为 1" },
    "text":     { "type": "string", "description": "片段原文" }
  }
}
```

### 2.3 UserProfile（用户资料）

0 号文件要求：字段、值、来源、未知或未填写状态。

```json
{
  "type": "object",
  "required": ["fields"],
  "additionalProperties": false,
  "properties": {
    "fields": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["key", "value", "source", "status"],
        "additionalProperties": false,
        "properties": {
          "key":    { "type": "string", "description": "资料字段名，如 '学历'" },
          "value":  { "type": ["string", "null"], "description": "字段值；未填写时为 null" },
          "source": { "type": "string", "enum": ["user_input", "extracted", "default"], "description": "值来源" },
          "status": { "type": "string", "enum": ["provided", "unknown", "empty"], "description": "填写状态" }
        }
      }
    }
  }
}
```

### 2.4 ConditionVerdict（条件判定）

严格对齐 `models.ConditionVerdict`。

```json
{
  "type": "object",
  "required": ["condition", "status", "rationale", "citations", "missing_info"],
  "additionalProperties": false,
  "properties": {
    "condition":    { "type": "string", "description": "条件名称" },
    "status":       { "$ref": "#/$defs/ConditionStatus" },
    "rationale":    { "type": "string", "description": "判定理由" },
    "citations":    { "type": "array", "items": { "$ref": "#/$defs/VerifiedCitation" }, "description": "证据关联" },
    "missing_info": { "type": "array", "items": { "type": "string" }, "description": "待补充信息" }
  }
}
```

### 2.5 VerifiedCitation（已核验引用）

对齐 `models.VerifiedCitation` + `models.Citation`，展平为前端可直接使用的结构。

```json
{
  "type": "object",
  "required": ["page", "quote", "verification_status", "coverage"],
  "additionalProperties": false,
  "properties": {
    "page":                { "type": "integer", "minimum": 1, "description": "引用所在页码" },
    "quote":               { "type": "string", "description": "引用原文" },
    "verification_status": { "$ref": "#/$defs/CitationStatus" },
    "coverage":            { "type": "number", "minimum": 0, "maximum": 1, "description": "引用与原文的覆盖率" },
    "is_trustworthy":      { "type": "boolean", "description": "VERIFIED 或 PARTIAL 为 true" }
  }
}
```

### 2.6 ChecklistItem（材料项）

后端当前 `checklist` 为 `tuple[str, ...]`，前端需要结构化。0 号文件要求名称、是否必需、依据、是否已提供。

```json
{
  "type": "object",
  "required": ["name", "required", "basis", "provided"],
  "additionalProperties": false,
  "properties": {
    "name":     { "type": "string", "description": "材料名称" },
    "required": { "type": "boolean", "description": "是否必需" },
    "basis":    { "type": "string", "description": "依据（对应政策条款）" },
    "provided": { "type": "boolean", "description": "用户是否已提供" }
  }
}
```

### 2.7 ActionStep（操作计划步骤）

对齐 `actions.Action` + 0 号文件要求的目标页面、动作、字段值、来源、确认要求、执行状态。

```json
{
  "type": "object",
  "required": ["step_index", "kind", "target", "risk", "requires_confirmation", "execution_status"],
  "additionalProperties": false,
  "properties": {
    "step_index":            { "type": "integer", "minimum": 0 },
    "kind":                  { "type": "string", "description": "动作类型：navigate / fill / select / upload / submit 等" },
    "target":                { "type": "string", "description": "目标页面或字段" },
    "value":                 { "type": ["string", "null"], "description": "字段值（敏感值只返回前 4 位 + 掩码）" },
    "source":                { "type": "string", "description": "值来源说明" },
    "note":                  { "type": "string", "description": "补充说明" },
    "risk":                  { "$ref": "#/$defs/RiskLevel" },
    "requires_confirmation": { "type": "boolean" },
    "execution_status":      { "type": "string", "enum": ["pending", "executed", "blocked", "skipped"], "description": "执行状态" },
    "detail":                { "type": ["string", "null"], "description": "执行结果描述" }
  }
}
```

### 2.8 ErrorResponse（错误响应）

对齐 `errors.py` 全部错误类型，0 号文件要求稳定错误标识、用户可读说明、能否重试及建议动作。

```json
{
  "type": "object",
  "required": ["error_code", "message", "retryable"],
  "additionalProperties": false,
  "properties": {
    "error_code":       { "type": "string", "description": "稳定的机器可读错误标识" },
    "message":          { "type": "string", "description": "用户可读的错误说明（中文）" },
    "retryable":        { "type": "boolean", "description": "是否可重试" },
    "suggested_action": { "type": ["string", "null"], "description": "建议的下一步操作" },
    "details":          { "type": ["object", "null"], "description": "错误详情（可选，调试用）" }
  }
}
```

---

## 三、状态枚举定义

### 3.1 ConditionStatus

对齐 `models.ConditionStatus`。

| 值 | 含义 | 前端显示 |
|---|---|---|
| `MET` | 原文明确支持，用户信息足以判定满足 | [满足] |
| `UNMET` | 原文明确支持，用户信息足以判定不满足 | [不满足] |
| `NEEDS_INPUT` | 原文清楚，但缺少用户关键信息 | [待补充] |
| `UNKNOWN` | 原文未说清，或证据核验未通过 | [原文未明确] |

### 3.2 CitationStatus

对齐 `models.CitationStatus`。

| 值 | 含义 | 前端显示 |
|---|---|---|
| `VERIFIED` | 在指定页面逐字匹配 | 已核验 |
| `PARTIAL` | 大部分匹配（覆盖率 ≥ 85%） | 基本一致 |
| `NOT_FOUND` | 在指定页面未找到 | 未能在该页找到 |
| `TOO_SHORT` | 引用不足 6 字符，不足为证 | 引用过短，不足为证 |
| `BAD_PAGE` | 引用的页码不存在 | 页码不存在 |

### 3.3 RiskLevel

对齐 `models.RiskLevel`。

| 值 | 含义 |
|---|---|
| `READ_ONLY` | 导航、读取、截图 |
| `LOCAL_WRITE` | 填写字段，可逆，未提交 |
| `SENSITIVE` | 提交、上传、支付、删除，需用户确认 |

### 3.4 DocumentStatus（新增，后端待实现）

| 值 | 含义 |
|---|---|
| `uploading` | 文件上传中 |
| `parsing` | 正在解析（调用 parser） |
| `ready` | 解析成功，可用于分析 |
| `failed` | 解析失败 |

### 3.5 AnalysisStatus（新增，后端待实现）

| 值 | 含义 |
|---|---|
| `pending` | 已创建，等待处理 |
| `retrieving` | 正在检索相关片段 |
| `reasoning` | 模型推理中 |
| `verifying` | 引用核验中 |
| `partial` | 部分可用（有结果但存在 NEEDS_INPUT） |
| `completed` | 分析完成 |
| `failed` | 分析失败 |

---

## 四、接口详细定义

---

### 4.1 上传政策文件

```
POST /api/documents
Content-Type: multipart/form-data
```

**请求**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | binary | 是 | 政策文件（支持 pdf, txt, md, docx, pptx, xlsx, html, png, jpg, jpeg） |

**响应 — 202 Accepted**

```json
{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "name": "policy.txt",
  "format": "txt",
  "status": "parsing",
  "parser": null,
  "page_count": 0,
  "chunk_count": 0,
  "content_hash": "a1b2c3d4e5f67890",
  "error": null,
  "created_at": "2026-09-13T10:00:00Z"
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 400 | `EMPTY_FILE` | 上传了空文件 |
| 415 | `UNSUPPORTED_FORMAT` | 不支持的文件类型（对应 `NoParserAvailableError`） |
| 413 | `FILE_TOO_LARGE` | 超出大小限制（上限待 C 确认） |
| 500 | `DOCUMENT_LOAD_ERROR` | 解析过程发生内部错误（对应 `DocumentLoadError`） |

---

### 4.2 查询文档详情

```
GET /api/documents/{doc_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `doc_id` | string | 文档标识 |

**响应 — 200 OK**

```json
{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "name": "policy.txt",
  "format": "txt",
  "status": "ready",
  "parser": "plaintext",
  "page_count": 2,
  "chunk_count": 2,
  "content_hash": "a1b2c3d4e5f67890",
  "error": null,
  "created_at": "2026-09-13T10:00:00Z"
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `DOCUMENT_NOT_FOUND` | doc_id 不存在 |

---

### 4.3 获取文档原文片段

```
GET /api/documents/{doc_id}/chunks
```

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page` | integer | 否 | 按页码过滤 |

**响应 — 200 OK**

```json
{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "chunks": [
    {
      "chunk_id": "policy-a1b2c3d4-p1-c0",
      "doc_id": "policy-a1b2c3d4e5f67890",
      "page": 1,
      "text": "市人才安居租房补贴实施细则(试行)\n\n第一章 总则\n\n第一条 为吸引和留住各类人才..."
    },
    {
      "chunk_id": "policy-a1b2c3d4-p2-c0",
      "doc_id": "policy-a1b2c3d4e5f67890",
      "page": 2,
      "text": "第三章 补贴标准\n\n第五条 补贴标准按学历和职称分档确定..."
    }
  ]
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `DOCUMENT_NOT_FOUND` | doc_id 不存在 |
| 409 | `DOCUMENT_NOT_READY` | 文档尚未解析完成 |

---

### 4.4 提交分析任务

```
POST /api/analyses
Content-Type: application/json
```

**请求体**

```json
{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "question": "我硕士毕业,28岁,在本市工作了8个月,社保交了8个月,名下没有房,已经网签备案了租房合同。我能申请多少补贴?需要准备什么?",
  "profile": {
    "fields": [
      { "key": "学历", "value": "硕士研究生", "source": "user_input", "status": "provided" },
      { "key": "年龄", "value": "28岁", "source": "user_input", "status": "provided" },
      { "key": "社保缴纳", "value": "本市连续8个月", "source": "user_input", "status": "provided" },
      { "key": "自有住房", "value": "无", "source": "user_input", "status": "provided" },
      { "key": "租赁备案", "value": "已完成网签备案", "source": "user_input", "status": "provided" }
    ]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `doc_id` | string | 是 | 关联文档标识 |
| `question` | string | 是 | 用户问题 |
| `profile` | UserProfile | 否 | 用户资料（首次可不传，步骤 2 再补充） |

**响应 — 202 Accepted**

```json
{
  "analysis_id": "ana_20260913_001",
  "doc_id": "policy-a1b2c3d4e5f67890",
  "status": "pending",
  "question": "我硕士毕业,28岁...我能申请多少补贴?",
  "profile": { "fields": [] },
  "result_url": "/api/analyses/ana_20260913_001/report",
  "error": null,
  "created_at": "2026-09-13T10:01:00Z"
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 400 | `MISSING_QUESTION` | question 为空 |
| 404 | `DOCUMENT_NOT_FOUND` | doc_id 不存在 |
| 409 | `DOCUMENT_NOT_READY` | 文档尚未解析完成 |
| 503 | `REASONER_UNAVAILABLE` | 模型不可用（对应 `ReasonerUnavailableError`） |

---

### 4.5 查询分析任务状态

```
GET /api/analyses/{analysis_id}
```

**响应 — 200 OK**

```json
{
  "analysis_id": "ana_20260913_001",
  "doc_id": "policy-a1b2c3d4e5f67890",
  "status": "completed",
  "question": "我硕士毕业,28岁...我能申请多少补贴?",
  "profile": {
    "fields": [
      { "key": "学历", "value": "硕士研究生", "source": "user_input", "status": "provided" },
      { "key": "年龄", "value": "28岁", "source": "user_input", "status": "provided" }
    ]
  },
  "result_url": "/api/analyses/ana_20260913_001/report",
  "error": null,
  "created_at": "2026-09-13T10:01:00Z",
  "completed_at": "2026-09-13T10:01:12Z"
}
```

> 前端用此接口轮询分析进度。当 `status` 为 `partial` 或 `completed` 时，可请求 report 接口获取结果。

**status = "failed" 时的响应**

```json
{
  "analysis_id": "ana_20260913_001",
  "doc_id": "policy-a1b2c3d4e5f67890",
  "status": "failed",
  "question": "...",
  "profile": { "fields": [] },
  "result_url": null,
  "error": {
    "error_code": "MODEL_REFUSED",
    "message": "模型拒绝了此请求，请调整问题措辞后重试。",
    "retryable": true,
    "suggested_action": "修改问题措辞后重新提交"
  },
  "created_at": "2026-09-13T10:01:00Z",
  "completed_at": null
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |

---

### 4.6 补充或修改用户资料

```
PATCH /api/analyses/{analysis_id}/profile
Content-Type: application/json
```

**请求体**

```json
{
  "fields": [
    { "key": "租赁合同备案日期", "value": "2026-06-01", "source": "user_input", "status": "provided" }
  ]
}
```

> PATCH 语义：传入的 fields 按 key 合并到现有 profile 中，相同 key 覆盖，新 key 追加。

**响应 — 200 OK**

返回合并后的完整 profile。

```json
{
  "fields": [
    { "key": "学历", "value": "硕士研究生", "source": "user_input", "status": "provided" },
    { "key": "年龄", "value": "28岁", "source": "user_input", "status": "provided" },
    { "key": "社保缴纳", "value": "本市连续8个月", "source": "user_input", "status": "provided" },
    { "key": "自有住房", "value": "无", "source": "user_input", "status": "provided" },
    { "key": "租赁备案", "value": "已完成网签备案", "source": "user_input", "status": "provided" },
    { "key": "租赁合同备案日期", "value": "2026-06-01", "source": "user_input", "status": "provided" }
  ]
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |
| 409 | `ANALYSIS_IN_PROGRESS` | 分析正在进行中，不能修改资料 |

---

### 4.7 补充资料后重新分析

```
POST /api/analyses/{analysis_id}/rerun
```

**请求体**：空（使用 analysis 上已有的最新 profile）

**响应 — 202 Accepted**

```json
{
  "analysis_id": "ana_20260913_001",
  "status": "pending",
  "message": "已使用更新后的资料重新提交分析"
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |
| 409 | `ANALYSIS_IN_PROGRESS` | 上一轮分析尚未完成 |
| 503 | `REASONER_UNAVAILABLE` | 模型不可用 |

---

### 4.8 获取完整分析报告

```
GET /api/analyses/{analysis_id}/report
```

**响应 — 200 OK**

对齐 `models.EligibilityReport` + `verifier.VerificationSummary`。

```json
{
  "analysis_id": "ana_20260913_001",
  "doc_id": "policy-a1b2c3d4e5f67890",
  "question": "我硕士毕业,28岁,在本市工作了8个月,社保交了8个月,名下没有房,已经网签备案了租房合同。我能申请多少补贴?需要准备什么?",
  "summary": "按你提供的信息,补贴标准对应每月1500元,主要条件均已满足,另有一项申请时限需要你补充确认。",
  "is_conclusive": false,
  "verdicts": [
    {
      "condition": "学历要求：全日制本科及以上学历，或中级及以上职称",
      "status": "MET",
      "rationale": "你是硕士研究生，符合本科及以上的学历要求。",
      "citations": [
        {
          "page": 1,
          "quote": "具有全日制本科及以上学历,或具有中级及以上专业技术职称",
          "verification_status": "VERIFIED",
          "coverage": 1.0,
          "is_trustworthy": true
        }
      ],
      "missing_info": []
    },
    {
      "condition": "年龄要求：申请时不超过35周岁",
      "status": "MET",
      "rationale": "你28岁，在35周岁上限之内。",
      "citations": [
        {
          "page": 1,
          "quote": "申请时年龄不超过35周岁",
          "verification_status": "VERIFIED",
          "coverage": 1.0,
          "is_trustworthy": true
        }
      ],
      "missing_info": []
    },
    {
      "condition": "社保要求：在本市连续缴纳社会保险满6个月",
      "status": "MET",
      "rationale": "你已连续缴纳8个月，超过6个月的下限。",
      "citations": [
        {
          "page": 1,
          "quote": "在本市连续缴纳\n社会保险满6个月",
          "verification_status": "VERIFIED",
          "coverage": 1.0,
          "is_trustworthy": true
        }
      ],
      "missing_info": []
    },
    {
      "condition": "补贴标准：硕士研究生每月1500元，且首次申请可追补3个月",
      "status": "UNKNOWN",
      "rationale": "按学历分档，硕士对应每月1500元，并可追补此前3个月。\n[证据核验未通过] 以下引用无法在原文中定位：第 2 页（NOT_FOUND，覆盖率 11%）。",
      "citations": [
        {
          "page": 2,
          "quote": "硕士研究生或副高级职称,每月1500元",
          "verification_status": "VERIFIED",
          "coverage": 1.0,
          "is_trustworthy": true
        },
        {
          "page": 2,
          "quote": "首次申请的人员可以追补此前3个月的补贴",
          "verification_status": "NOT_FOUND",
          "coverage": 0.11,
          "is_trustworthy": false
        }
      ],
      "missing_info": []
    },
    {
      "condition": "劳动合同期限不少于1年",
      "status": "UNKNOWN",
      "rationale": "你与本市用人单位已建立劳动关系。\n[证据核验未通过] 以下引用无法在原文中定位：第 1 页（TOO_SHORT，覆盖率 0%）。",
      "citations": [
        {
          "page": 1,
          "quote": "合同",
          "verification_status": "TOO_SHORT",
          "coverage": 0.0,
          "is_trustworthy": false
        }
      ],
      "missing_info": []
    },
    {
      "condition": "申请时限：租赁合同备案之日起6个月内提出申请",
      "status": "NEEDS_INPUT",
      "rationale": "原文对申请时限有硬性要求，但你没有说明备案的具体日期。",
      "citations": [
        {
          "page": 2,
          "quote": "申请人应当在租赁合同备案之日起6个月内提出申请,逾期不再受理",
          "verification_status": "VERIFIED",
          "coverage": 1.0,
          "is_trustworthy": true
        }
      ],
      "missing_info": ["住房租赁合同网签备案的具体日期"]
    }
  ],
  "checklist": [
    {
      "name": "租房补贴申请表（在线填写并打印签字）",
      "required": true,
      "basis": "第七条第一项",
      "provided": false
    },
    {
      "name": "身份证正反面复印件",
      "required": true,
      "basis": "第七条第二项",
      "provided": false
    },
    {
      "name": "硕士学历学位证书（国外学历需教育部留学服务中心认证书）",
      "required": true,
      "basis": "第七条第三项",
      "provided": false
    },
    {
      "name": "劳动合同复印件",
      "required": true,
      "basis": "第七条第四项",
      "provided": false
    },
    {
      "name": "近6个月社会保险缴纳记录",
      "required": true,
      "basis": "第七条第五项",
      "provided": false
    },
    {
      "name": "住房租赁合同网签备案证明",
      "required": true,
      "basis": "第七条第六项",
      "provided": false
    },
    {
      "name": "本人名下本市银行账户信息",
      "required": true,
      "basis": "第七条第七项",
      "provided": false
    }
  ],
  "verification_summary": {
    "total_citations": 7,
    "verified": 5,
    "partial": 0,
    "rejected": 2,
    "downgraded_conditions": 2,
    "rejection_rate": 0.2857
  },
  "missing_inputs": ["住房租赁合同网签备案的具体日期"],
  "counts": {
    "MET": 3,
    "UNMET": 0,
    "NEEDS_INPUT": 1,
    "UNKNOWN": 2
  }
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |
| 409 | `REPORT_NOT_READY` | 分析尚未完成（status 不是 partial/completed） |

---

### 4.9 获取单条判定的引用原文上下文

```
GET /api/analyses/{analysis_id}/citations/{verdict_index}
```

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `verdict_index` | integer | 判定在 verdicts 数组中的索引（0-based） |

**响应 — 200 OK**

为每条引用返回其在文档原文中的上下文定位。

```json
{
  "verdict_index": 0,
  "condition": "学历要求：全日制本科及以上学历，或中级及以上职称",
  "citations": [
    {
      "page": 1,
      "quote": "具有全日制本科及以上学历,或具有中级及以上专业技术职称",
      "verification_status": "VERIFIED",
      "coverage": 1.0,
      "context_before": "第三条 申请人应当同时符合以下条件：\n\n（一）",
      "context_after": "；\n\n（二）申请时年龄不超过35周岁",
      "char_offset": 120,
      "page_text_length": 390
    }
  ]
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |
| 404 | `VERDICT_NOT_FOUND` | verdict_index 越界 |
| 409 | `REPORT_NOT_READY` | 报告尚未生成 |

---

### 4.10 获取操作计划

```
GET /api/analyses/{analysis_id}/plan
```

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target_url` | string | 是 | 目标申请页面 URL |

**响应 — 200 OK**

```json
{
  "analysis_id": "ana_20260913_001",
  "target_url": "https://example.gov.cn/apply",
  "risk_summary": {
    "READ_ONLY": 1,
    "LOCAL_WRITE": 2,
    "SENSITIVE": 2
  },
  "steps": [
    {
      "step_index": 0,
      "kind": "navigate",
      "target": "https://example.gov.cn/apply",
      "value": null,
      "source": "用户指定",
      "note": "",
      "risk": "READ_ONLY",
      "requires_confirmation": false,
      "execution_status": "pending",
      "detail": null
    },
    {
      "step_index": 1,
      "kind": "fill",
      "target": "申请人姓名",
      "value": null,
      "source": "待用户填写",
      "note": "",
      "risk": "LOCAL_WRITE",
      "requires_confirmation": false,
      "execution_status": "pending",
      "detail": null
    },
    {
      "step_index": 2,
      "kind": "fill",
      "target": "身份证号",
      "value": null,
      "source": "待用户填写",
      "note": "",
      "risk": "LOCAL_WRITE",
      "requires_confirmation": false,
      "execution_status": "pending",
      "detail": null
    },
    {
      "step_index": 3,
      "kind": "upload",
      "target": "学历学位证书",
      "value": null,
      "source": "材料清单第 3 项",
      "note": "",
      "risk": "SENSITIVE",
      "requires_confirmation": true,
      "execution_status": "pending",
      "detail": null
    },
    {
      "step_index": 4,
      "kind": "submit",
      "target": "提交申请",
      "value": null,
      "source": "",
      "note": "",
      "risk": "SENSITIVE",
      "requires_confirmation": true,
      "execution_status": "pending",
      "detail": null
    }
  ]
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |
| 409 | `REPORT_NOT_READY` | 报告尚未完成 |

---

### 4.11 确认敏感操作

```
POST /api/analyses/{analysis_id}/plan/confirm
Content-Type: application/json
```

**请求体**

```json
{
  "step_index": 3,
  "confirmed": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `step_index` | integer | 是 | 待确认的步骤索引 |
| `confirmed` | boolean | 是 | 用户是否确认执行 |

**响应 — 200 OK**

```json
{
  "step_index": 3,
  "execution_status": "executed",
  "detail": "已上传学历学位证书"
}
```

**错误响应**

| 状态码 | error_code | 场景 |
|---|---|---|
| 404 | `ANALYSIS_NOT_FOUND` | analysis_id 不存在 |
| 400 | `STEP_NOT_SENSITIVE` | 该步骤不需要确认 |
| 409 | `CONFIRMATION_REQUIRED` | 尝试执行敏感操作但未确认（对应 `ConfirmationRequiredError`） |
| 409 | `STEP_ALREADY_EXECUTED` | 该步骤已执行 |

---

## 五、错误响应统一格式与错误码映射

所有非 2xx 响应使用统一的 ErrorResponse 结构。

### 5.1 错误码映射表

从后端 `errors.py` 异常类到 HTTP 错误码的完整映射：

| 后端异常 | error_code | HTTP 状态码 | retryable | 用户可读说明 | suggested_action |
|---|---|---|---|---|---|
| `DocumentLoadError` | `DOCUMENT_LOAD_ERROR` | 500 | false | 文件解析失败：{detail} | 检查文件是否损坏或更换格式 |
| `NoParserAvailableError` | `UNSUPPORTED_FORMAT` | 415 | false | 不支持该文件格式 | 上传 PDF 或 TXT 格式文件 |
| `EmptyIndexError` | `EMPTY_INDEX` | 422 | false | 文档未提取到有效文本 | 确认文件包含可读文本内容 |
| `ReasonerUnavailableError` | `REASONER_UNAVAILABLE` | 503 | true | 分析服务暂时不可用 | 请稍后重试 |
| `ModelRefusedError` | `MODEL_REFUSED` | 422 | true | 模型拒绝了此请求 | 修改问题措辞后重新提交 |
| `MalformedModelOutputError` | `MALFORMED_OUTPUT` | 502 | true | 分析结果格式异常 | 请重试，若反复出现请联系管理员 |
| `ConfirmationRequiredError` | `CONFIRMATION_REQUIRED` | 409 | false | 此操作需要用户确认 | 确认后重新提交 |
| `AuditChainBrokenError` | `AUDIT_CHAIN_BROKEN` | 500 | false | 审计链完整性校验失败 | 联系管理员检查审计日志 |
| — | `DOCUMENT_NOT_FOUND` | 404 | false | 文档不存在 | 检查文档标识是否正确 |
| — | `ANALYSIS_NOT_FOUND` | 404 | false | 分析任务不存在 | 检查任务标识是否正确 |
| — | `DOCUMENT_NOT_READY` | 409 | true | 文档尚未解析完成 | 等待解析完成后重试 |
| — | `REPORT_NOT_READY` | 409 | true | 分析报告尚未生成 | 等待分析完成后重试 |
| — | `ANALYSIS_IN_PROGRESS` | 409 | false | 分析正在进行中 | 等待当前分析完成 |
| — | `EMPTY_FILE` | 400 | false | 上传的文件内容为空 | 选择非空文件重新上传 |
| — | `FILE_TOO_LARGE` | 413 | false | 文件超过大小限制 | 压缩文件或拆分上传 |
| — | `MISSING_QUESTION` | 400 | false | 问题不能为空 | 输入问题后重新提交 |
| — | `VERDICT_NOT_FOUND` | 404 | false | 指定的判定条目不存在 | 检查判定索引是否正确 |
| — | `STEP_NOT_SENSITIVE` | 400 | false | 该步骤不需要确认 | 无需确认，直接执行 |
| — | `STEP_ALREADY_EXECUTED` | 409 | false | 该步骤已执行完成 | 无需重复执行 |

### 5.2 错误响应示例

```json
{
  "error_code": "REASONER_UNAVAILABLE",
  "message": "分析服务暂时不可用：rate limited",
  "retryable": true,
  "suggested_action": "请稍后重试",
  "details": {
    "original_error": "ReasonerUnavailableError",
    "inner_message": "rate limited: ..."
  }
}
```

---

## 六、前端重点关注的状态与轮询策略

### 6.1 文件上传状态流转

```
上传中             解析中              就绪
uploading ──────► parsing ──────► ready
                    │
                    └──────────► failed（解析失败）
```

- 前端在 `POST /api/documents` 返回后，轮询 `GET /api/documents/{doc_id}` 直到 `status` 变为 `ready` 或 `failed`。
- 建议轮询间隔：1 秒，上限 60 秒后超时。

### 6.2 分析任务状态流转

```
pending ──► retrieving ──► reasoning ──► verifying ──► completed
                                │                         │
                                │                    partial（有 NEEDS_INPUT）
                                │
                                └──────────────────► failed
```

- `partial` 表示分析完成但存在 `NEEDS_INPUT` 判定，前端可展示已有结果并引导用户补充资料。
- 前端在 `POST /api/analyses` 返回后，轮询 `GET /api/analyses/{analysis_id}` 直到状态终止。
- 建议轮询间隔：2 秒（reasoning 阶段可能耗时较长），上限 120 秒后超时。

### 6.3 证据定位失败的处理

当 `verification_status` 为 `NOT_FOUND`、`BAD_PAGE` 或 `TOO_SHORT` 时：
- 前端在对应的判定条目上标注"证据核验未通过"警示。
- 如果该判定因此被降级（原状态为 MET/UNMET，现状态为 UNKNOWN），在 rationale 中会包含 `[证据核验未通过]` 前缀。
- `verification_summary.downgraded_conditions > 0` 时，在报告顶部显示全局降级提示。

---

## 七、前端需要 C 确认的待定项清单

| # | 待定项 | 前端假设 | 需要 C 确认的内容 |
|---|--------|---------|------------------|
| 1 | **文件大小上限** | 前端不限制，由后端拒绝 | 后端接受的最大文件大小是多少？前端是否需要在上传前校验？ |
| 2 | **analysis_id 生成规则** | 由后端生成，前端作为不透明字符串使用 | 具体格式？是否 UUID？ |
| 3 | **轮询 vs WebSocket** | 前端默认使用轮询 | 后端是否计划支持 WebSocket 或 SSE 推送分析进度？如果支持，接口路径是什么？ |
| 4 | **checklist 结构化** | 后端当前 `checklist` 是 `tuple[str, ...]`，前端需要 `ChecklistItem` 结构（含 required / basis / provided 字段） | C 是否在后端完成结构化，还是前端自行解析字符串？ |
| 5 | **profile 到 dict 的转换** | 后端 `reasoner.analyze()` 接受 `profile: dict[str, Any]`，前端发送的 `UserProfile.fields` 需要后端转换为 `{key: value}` 字典 | C 确认后端做此转换 |
| 6 | **VerifiedCitation 展平** | 前端需要展平的 `{page, quote, verification_status, coverage}` 而非嵌套的 `{citation: {page, quote}, status, coverage}` | C 确认序列化时展平，还是前端自行解嵌套？ |
| 7 | **原文上下文接口** | 接口 4.9 返回引用在页面中的前后文（`context_before`、`context_after`、`char_offset`） | C 确认可以提供定位信息？上下文截取长度建议多少字符？ |
| 8 | **操作计划是否属于 MVP** | 接口 4.10 和 4.11 涉及 `browser-use` 可选组件 | C 确认 plan/confirm 接口是否纳入首轮联调？若推迟，前端步骤 4 先只展示原文和材料清单 |
| 9 | **并发限制** | 前端允许用户对同一文档发起多次分析 | 后端是否限制同一 doc_id 的并发分析数？ |
| 10 | **分析结果持久化** | 前端假设 analysis_id 在会话期间有效 | 后端是否持久化分析结果？过期策略？重启后是否丢失？ |
| 11 | **非 PDF 的页码语义** | 纯文本用 `--- PAGE BREAK ---` 分页，page 为分段序号；无分页标记时 page=1 | C 确认前端可以安全地对所有格式显示"第 N 页"，还是非 PDF 需要显示"第 N 段"？ |
| 12 | **多文档分析** | 当前每次分析绑定一个 doc_id | 后续是否需要支持多文档关联分析？目前前端按单文档设计 |
| 13 | **国际化** | 后端错误 message 和 rationale 固定为中文 | C 确认首版只支持中文，无需 i18n 接口 |
| 14 | **AnalysisStatus 中间态** | 前端需要 `retrieving` / `reasoning` / `verifying` 展示进度条 | C 确认后端会更新这些中间状态，还是只有 `pending` → `completed/failed` 两态？ |
| 15 | **CORS 配置** | 前后端同域部署或后端允许前端域的跨域请求 | C 确认 CORS 策略 |
| 16 | **认证方式** | 首版无认证 | C 确认首版是否需要任何形式的用户认证或会话管理？ |

---

## 附录 A：四步页面与接口调用时序

```
┌─────────────────────────────────────────────────────────────────────┐
│  步骤 1：文件与问题输入                                               │
│                                                                     │
│  用户选择文件 ──► POST /api/documents                                │
│  轮询解析状态 ──► GET  /api/documents/{doc_id}                       │
│  文件就绪后输入问题 + 初始资料                                         │
│  提交分析     ──► POST /api/analyses                                 │
├─────────────────────────────────────────────────────────────────────┤
│  步骤 2：资料补充                                                     │
│                                                                     │
│  轮询分析状态 ──► GET  /api/analyses/{analysis_id}                   │
│  status=partial 时展示已有结果 + missing_inputs                      │
│  用户补充资料 ──► PATCH /api/analyses/{analysis_id}/profile          │
│  重新分析     ──► POST  /api/analyses/{analysis_id}/rerun            │
├─────────────────────────────────────────────────────────────────────┤
│  步骤 3：分析结果                                                     │
│                                                                     │
│  status=completed 时获取报告                                          │
│  展示报告     ──► GET  /api/analyses/{analysis_id}/report            │
│  显示判定列表、材料清单、证据核验摘要                                   │
├─────────────────────────────────────────────────────────────────────┤
│  步骤 4：原文与行动                                                   │
│                                                                     │
│  查看引用原文 ──► GET  /api/analyses/{analysis_id}/citations/{i}     │
│  查看文档片段 ──► GET  /api/documents/{doc_id}/chunks                │
│  查看操作计划 ──► GET  /api/analyses/{analysis_id}/plan              │
│  确认敏感操作 ──► POST /api/analyses/{analysis_id}/plan/confirm      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 附录 B：完整请求/响应样例数据

以下样例基于内置演示数据（`examples/policy.txt` + `demo.py` 的预设报告，经 `verifier.py` 核验后的真实结果）。

### B.1 上传文件

**请求**

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=----boundary

------boundary
Content-Disposition: form-data; name="file"; filename="policy.txt"
Content-Type: text/plain

市人才安居租房补贴实施细则(试行)
...（省略文件内容）
------boundary--
```

**响应**

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "name": "policy.txt",
  "format": "txt",
  "status": "parsing",
  "parser": null,
  "page_count": 0,
  "chunk_count": 0,
  "content_hash": "a1b2c3d4e5f67890",
  "error": null,
  "created_at": "2026-09-13T10:00:00Z"
}
```

### B.2 查询文档（就绪后）

**响应**

```http
HTTP/1.1 200 OK

{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "name": "policy.txt",
  "format": "txt",
  "status": "ready",
  "parser": "plaintext",
  "page_count": 2,
  "chunk_count": 2,
  "content_hash": "a1b2c3d4e5f67890",
  "error": null,
  "created_at": "2026-09-13T10:00:00Z"
}
```

### B.3 提交分析

**请求**

```http
POST /api/analyses HTTP/1.1
Content-Type: application/json

{
  "doc_id": "policy-a1b2c3d4e5f67890",
  "question": "我硕士毕业,28岁,在本市工作了8个月,社保交了8个月,名下没有房,已经网签备案了租房合同。我能申请多少补贴?需要准备什么?",
  "profile": {
    "fields": [
      { "key": "学历", "value": "硕士研究生", "source": "user_input", "status": "provided" },
      { "key": "年龄", "value": "28岁", "source": "user_input", "status": "provided" },
      { "key": "社保缴纳", "value": "本市连续8个月", "source": "user_input", "status": "provided" },
      { "key": "自有住房", "value": "无", "source": "user_input", "status": "provided" },
      { "key": "租赁备案", "value": "已完成网签备案", "source": "user_input", "status": "provided" }
    ]
  }
}
```

**响应**

```http
HTTP/1.1 202 Accepted

{
  "analysis_id": "ana_20260913_001",
  "doc_id": "policy-a1b2c3d4e5f67890",
  "status": "pending",
  "question": "我硕士毕业,28岁...我能申请多少补贴?",
  "profile": {
    "fields": [
      { "key": "学历", "value": "硕士研究生", "source": "user_input", "status": "provided" },
      { "key": "年龄", "value": "28岁", "source": "user_input", "status": "provided" },
      { "key": "社保缴纳", "value": "本市连续8个月", "source": "user_input", "status": "provided" },
      { "key": "自有住房", "value": "无", "source": "user_input", "status": "provided" },
      { "key": "租赁备案", "value": "已完成网签备案", "source": "user_input", "status": "provided" }
    ]
  },
  "result_url": "/api/analyses/ana_20260913_001/report",
  "error": null,
  "created_at": "2026-09-13T10:01:00Z"
}
```

### B.4 补充资料

**请求**

```http
PATCH /api/analyses/ana_20260913_001/profile HTTP/1.1
Content-Type: application/json

{
  "fields": [
    { "key": "租赁合同备案日期", "value": "2026-06-01", "source": "user_input", "status": "provided" }
  ]
}
```

**响应**

```http
HTTP/1.1 200 OK

{
  "fields": [
    { "key": "学历", "value": "硕士研究生", "source": "user_input", "status": "provided" },
    { "key": "年龄", "value": "28岁", "source": "user_input", "status": "provided" },
    { "key": "社保缴纳", "value": "本市连续8个月", "source": "user_input", "status": "provided" },
    { "key": "自有住房", "value": "无", "source": "user_input", "status": "provided" },
    { "key": "租赁备案", "value": "已完成网签备案", "source": "user_input", "status": "provided" },
    { "key": "租赁合同备案日期", "value": "2026-06-01", "source": "user_input", "status": "provided" }
  ]
}
```

### B.5 重新分析

**请求**

```http
POST /api/analyses/ana_20260913_001/rerun HTTP/1.1
```

**响应**

```http
HTTP/1.1 202 Accepted

{
  "analysis_id": "ana_20260913_001",
  "status": "pending",
  "message": "已使用更新后的资料重新提交分析"
}
```

### B.6 获取报告（完整响应见第四节 4.8 的样例）

略，参见第四节 4.8。

### B.7 查看引用原文上下文

**请求**

```http
GET /api/analyses/ana_20260913_001/citations/0 HTTP/1.1
```

**响应**

```http
HTTP/1.1 200 OK

{
  "verdict_index": 0,
  "condition": "学历要求：全日制本科及以上学历，或中级及以上职称",
  "citations": [
    {
      "page": 1,
      "quote": "具有全日制本科及以上学历,或具有中级及以上专业技术职称",
      "verification_status": "VERIFIED",
      "coverage": 1.0,
      "context_before": "第三条 申请人应当同时符合以下条件：\n\n（一）",
      "context_after": "；\n\n（二）申请时年龄不超过35周岁，其中具有博士学位的不超过40周岁；",
      "char_offset": 120,
      "page_text_length": 390
    }
  ]
}
```

### B.8 错误响应样例

**文件格式不支持**

```http
HTTP/1.1 415 Unsupported Media Type

{
  "error_code": "UNSUPPORTED_FORMAT",
  "message": "不支持该文件格式：.exe",
  "retryable": false,
  "suggested_action": "上传 PDF 或 TXT 格式文件",
  "details": null
}
```

**模型不可用**

```http
HTTP/1.1 503 Service Unavailable

{
  "error_code": "REASONER_UNAVAILABLE",
  "message": "分析服务暂时不可用：rate limited",
  "retryable": true,
  "suggested_action": "请稍后重试",
  "details": {
    "original_error": "ReasonerUnavailableError",
    "inner_message": "rate limited: request limit exceeded"
  }
}
```

**需要用户确认**

```http
HTTP/1.1 409 Conflict

{
  "error_code": "CONFIRMATION_REQUIRED",
  "message": "此操作需要用户确认：action 'submit -> 提交申请' is SENSITIVE and requires explicit user confirmation",
  "retryable": false,
  "suggested_action": "确认后重新提交",
  "details": {
    "action_name": "submit -> 提交申请",
    "risk": "SENSITIVE"
  }
}
```
