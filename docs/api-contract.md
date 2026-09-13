# ProofPath API 契约

版本：0.1-draft ｜ 负责人：C ｜ 评审人：A、D、E

本文定义 P05 的前后端边界。它是评审草案，不表示 HTTP 适配器、持久化或后台任务已经实现。首版面向单机、单用户、受控演示环境；未经身份认证与租户隔离评审，不得部署为公网多用户服务。

## 1. 不可破坏的约束

1. 模型生成的判断不得直接返回。服务端必须先调用唯一的 `verify_report` 核验入口。
2. `MET`、`UNMET` 只有在引用核验通过后才能出现在最终结果中；失败时降级为 `UNKNOWN`。
3. 分析结果的 `document_id` 必须与请求文档一致；不一致时整个任务失败，不得跨文档核验。
4. 页码从 1 开始。没有真实页码的文本只允许使用其解析后页序，不伪造原文件页码。
5. 服务端密钥、完整个人敏感资料和原始模型响应不得写入普通日志或错误响应。
6. 首版不执行真实申请提交、付款或删除。任何未来敏感动作必须经过 `ActionGate` 和逐项确认。
7. 模型生成的总摘要和材料字符串不直接返回；摘要由核验后的状态计数生成，材料在逐项溯源完成前返回空数组。
8. 当前核验只确认引用位置，不证明引用在语义上支持结论。只要结果中仍有 `MET` 或 `UNMET`，必须返回 `requires_human_review: true`，任务状态使用 `PARTIAL`。
9. 判断因引用失败被降级时，服务端必须替换模型生成的原理由，只返回程序生成的核验失败说明。

## 2. HTTP 通用规则

- 基础路径：`/api/v1`
- JSON 编码：UTF-8，时间使用 UTC RFC 3339，例如 `2026-09-13T08:00:00Z`
- 成功响应直接返回资源对象；失败响应统一使用第 6 节错误对象。
- 除文件上传外，请求和响应均使用 `application/json`。
- 文件上传使用 `multipart/form-data`，字段名固定为 `file`。
- `POST /analyses` 必须携带 `Idempotency-Key` 请求头，长度为 16–128 个可打印 ASCII 字符。
- 服务生成的 ID 是不透明字符串。客户端不得解析 ID、猜测顺序或自行构造资源地址。

## 3. 数据对象

除非字段表明确写“否”或“可为 `null`”，下列示例中的字段均为必填字段；客户端必须容忍未来增加的新字段，但不能忽略未知枚举值。对象来源由各字段表或对象说明给出，模型推测不得伪装成用户输入或程序核验结果。

### 3.1 Document

```json
{
  "document_id": "housing-policy-a13f40c26df1a170",
  "filename": "住房补贴政策.pdf",
  "media_type": "application/pdf",
  "parser": "pypdf",
  "page_count": 6,
  "created_at": "2026-09-13T08:00:00Z"
}
```

| 字段 | 类型 | 必填 | 来源与含义 |
|---|---|:---:|---|
| `document_id` | string | 是 | 服务端按文件内容生成的不透明标识 |
| `filename` | string | 是 | 客户端文件名，仅用于显示；不得作为服务端路径 |
| `media_type` | string | 是 | 服务端实际识别或校验后的媒体类型 |
| `parser` | string | 是 | 实际使用的解析器，例如 `pypdf`、`plaintext` |
| `page_count` | integer | 是 | 解析后的页数，最小为 1 |
| `created_at` | string | 是 | 服务端创建时间 |

### 3.2 SourceFragment

```json
{
  "fragment_id": "housing-policy-a13f40c26df1a170-p2-c0",
  "document_id": "housing-policy-a13f40c26df1a170",
  "page": 2,
  "text": "第五条 补贴标准……"
}
```

| 字段 | 类型 | 必填 | 来源与含义 |
|---|---|:---:|---|
| `fragment_id` | string | 是 | 服务端解析时生成的稳定片段标识 |
| `document_id` | string | 是 | 片段所属文档，必须与请求文档一致 |
| `page` | integer | 是 | 解析后页序，从 1 开始 |
| `text` | string | 是 | 该片段的原文，不包含模型改写 |

### 3.3 ProfileField

```json
{
  "key": "年龄",
  "value": "28",
  "state": "PROVIDED",
  "source": "USER_INPUT"
}
```

| 字段 | 类型 | 必填 | 来源与含义 |
|---|---|:---:|---|
| `key` | string | 是 | 产品或用户给出的资料项名称 |
| `value` | string/null | 是 | `PROVIDED` 时为非空字符串，其他状态必须为 `null` |
| `state` | enum | 是 | `PROVIDED`、`UNKNOWN` 或 `DECLINED` |
| `source` | enum | 是 | 首版只允许 `USER_INPUT` |

服务端不得把模型推测写成用户资料；`UNKNOWN` 表示尚未填写，`DECLINED` 表示用户明确不愿提供。

### 3.4 Citation

```json
{
  "page": 2,
  "fragment_id": "housing-policy-a13f40c26df1a170-p2-c0",
  "quote": "硕士研究生或副高级职称，每月1500元",
  "status": "VERIFIED",
  "coverage": 1.0,
  "locator": "/api/v1/documents/housing-policy-a13f40c26df1a170/pages/2"
}
```

`status` 只允许：

- `VERIFIED`：归一化后逐字定位成功。
- `PARTIAL`：大部分可定位，但存在抽取或转写差异；前端必须显示风险提示。
- `NOT_FOUND`：无法定位。
- `TOO_SHORT`：引用过短，不足以作为证据。
- `BAD_PAGE`：页码不存在。

`coverage` 范围为 0.0–1.0。客户端不得根据覆盖率自行改变资格状态。

当前运行时把 `VERIFIED` 和 `PARTIAL` 都视为“位置可核验”，但 `PARTIAL` 必须显示风险提示，并使整个分析任务至少为 `PARTIAL`；它不代表语义支持已经通过。

### 3.5 ConditionVerdict

```json
{
  "condition": "申请时年龄不超过35周岁",
  "status": "MET",
  "rationale": "用户填写年龄为28岁，低于政策上限。",
  "citations": [
    {
      "page": 1,
      "fragment_id": "housing-policy-a13f40c26df1a170-p1-c0",
      "quote": "申请时年龄不超过35周岁",
      "status": "VERIFIED",
      "coverage": 1.0,
      "locator": "/api/v1/documents/housing-policy-a13f40c26df1a170/pages/1"
    }
  ],
  "missing_info": []
}
```

`status` 只允许：

- `MET`：原文明示条件，用户资料足够且核验后判断满足。
- `UNMET`：原文明示条件，用户资料足够且核验后判断不满足。
- `NEEDS_INPUT`：原文条件明确，但缺少用户信息。
- `UNKNOWN`：原文不足、检索不足或证据核验失败。

`NEEDS_INPUT` 必须给出非空 `missing_info`。`MET`、`UNMET` 必须至少有一条可信引用。客户端只负责展示，不能重新计算状态。

### 3.6 MaterialItem

```json
{
  "name": "硕士学历学位证书",
  "basis": "POLICY_TEXT",
  "requirement_state": "REQUIRED",
  "provision_state": "NOT_PROVIDED",
  "citations": [
    {
      "page": 2,
      "fragment_id": "housing-policy-a13f40c26df1a170-p2-c0",
      "quote": "学历学位证书",
      "status": "VERIFIED",
      "coverage": 1.0,
      "locator": "/api/v1/documents/housing-policy-a13f40c26df1a170/pages/2"
    }
  ]
}
```

`basis` 只允许 `POLICY_TEXT` 或 `USER_INPUT`；`requirement_state` 只允许 `REQUIRED`、`CONDITIONAL`、`UNKNOWN`；`provision_state` 只允许 `PROVIDED`、`NOT_PROVIDED`、`DECLINED`、`NOT_APPLICABLE`。现有核心的材料清单仍是未经逐项溯源的字符串；升级为本对象前，接口适配器必须返回空的 `materials`，不得把模型生成的字符串标成政策原文依据，也不得伪造引用。

### 3.7 AnalysisTask

```json
{
  "analysis_id": "ana_01J7A4V24V9J2X3A",
  "document_id": "housing-policy-a13f40c26df1a170",
  "state": "PARTIAL",
  "question": "我能申请多少补贴？",
  "profile": [
    {"key": "年龄", "value": "28", "state": "PROVIDED", "source": "USER_INPUT"}
  ],
  "result": {
    "summary": "证据核验结果：满足 1 项，不满足 0 项，需补充信息 0 项，原文未明确 0 项。当前仅核对引用位置，结论语义仍需人工复核。",
    "verdicts": [
      {
        "condition": "申请时年龄不超过35周岁",
        "status": "MET",
        "rationale": "用户填写年龄为28岁，低于政策上限。",
        "citations": [
          {
            "page": 1,
            "fragment_id": "housing-policy-a13f40c26df1a170-p1-c0",
            "quote": "申请时年龄不超过35周岁",
            "status": "VERIFIED",
            "coverage": 1.0,
            "locator": "/api/v1/documents/housing-policy-a13f40c26df1a170/pages/1"
          }
        ],
        "missing_info": []
      }
    ],
    "materials": [],
    "missing_inputs": [],
    "requires_human_review": true
  },
  "error": null,
  "created_at": "2026-09-13T08:01:00Z",
  "updated_at": "2026-09-13T08:01:03Z"
}
```

`state` 只允许：

- `RUNNING`：任务已接受，尚无最终结果。
- `SUCCEEDED`：已得到经过位置核验且无需人工语义复核的完整结果。
- `PARTIAL`：任务完成，但至少一项为 `NEEDS_INPUT`、`UNKNOWN`、使用 `PARTIAL` 引用，或 `requires_human_review` 为 `true`。
- `FAILED`：无法形成可安全展示的结果，必须提供 `error`。
- `CANCELLED`：在完成前成功取消；不得返回伪造或旧的 `result`。

状态转换：

```text
RUNNING -> SUCCEEDED | PARTIAL | FAILED | CANCELLED
```

终态不可再次变化。同一任务不得从 `FAILED` 自动跳回 `RUNNING`；重试必须创建新任务并使用新的幂等键。终态字段约束：

- `SUCCEEDED`、`PARTIAL`：`result` 非空、`error` 为 `null`。
- `FAILED`：`result` 为 `null`、`error` 非空。
- `CANCELLED`：`result` 与 `error` 均为 `null`。
- 核验后没有任何条件判断时，任务使用 `PARTIAL`，摘要说明“未形成可核验的条件判断”。

### 3.8 Error 与 ErrorEnvelope

```json
{
  "code": "NO_EXTRACTABLE_TEXT",
  "message": "文件中没有可提取文本，可能是扫描件。",
  "retryable": false,
  "suggested_action": "请上传带文本层的 PDF，或在启用 OCR 后重试。",
  "request_id": "req_01J7A4W5AR"
}
```

`AnalysisTask.error` 使用上面的裸 `Error` 对象。HTTP 非成功响应使用 `{"error": <Error>}` 作为唯一的 `ErrorEnvelope`，不会出现 `{"error": {"error": ...}}` 双重包装。

### 3.9 ActionPlan

```json
{
  "actions": [
    {
      "action_id": "act_01J7A6",
      "kind": "fill",
      "target": "申请人年龄",
      "target_url": "https://example.invalid/application",
      "value_preview": "28",
      "source": "USER_INPUT",
      "risk": "LOCAL_WRITE",
      "requires_confirmation": false,
      "state": "PLANNED"
    }
  ]
}
```

该对象为 P10 预留，不属于本轮 HTTP 实现。`risk` 只允许 `READ_ONLY`、`LOCAL_WRITE`、`SENSITIVE`；未知动作一律为 `SENSITIVE`。`state` 只允许 `PLANNED`、`REQUIRES_CONFIRMATION`、`CONFIRMED`、`EXECUTED`、`CANCELLED`、`FAILED`。`target_url` 是动作对应页面，不得包含凭证；表单字段由 `target` 标识。

## 4. 接口

### 4.1 上传并解析文档

`POST /api/v1/documents`

- 支持：`.pdf`、`.txt`、`.md`。
- 单文件上限：20 MiB。
- 空文件、损坏文件、无文本文件和不支持类型必须返回明确错误。
- 文件名只用于显示；服务端必须忽略其中的目录部分。

成功：`201 Created`，响应为 `Document`。

### 4.2 创建分析任务

`POST /api/v1/analyses`

```json
{
  "document_id": "housing-policy-a13f40c26df1a170",
  "question": "我能申请多少补贴？",
  "profile": [
    {"key": "年龄", "value": "28", "state": "PROVIDED", "source": "USER_INPUT"}
  ]
}
```

约束：

- `question` 去除首尾空白后长度为 1–2000 个 Unicode 字符。
- `profile` 最多 50 项；键去除空白后不得为空，同一键不得重复。
- 接受任务后返回 `202 Accepted` 和 `AnalysisTask`，初始状态为 `RUNNING`。
- 若实现选择同步完成，也仍返回任务对象；状态可以直接是终态。

#### 幂等规则

`Idempotency-Key` 是必需请求头：

- 相同键、相同规范化请求体：返回原任务，不能重复调用模型或重复计费。
- 相同键、不同请求体：返回 `409 IDEMPOTENCY_CONFLICT`。
- 键至少保留 24 小时。服务重启后若无法保留，部署说明必须明确标记“仅进程内幂等”，不得宣称跨重启可靠。

### 4.3 查询分析任务

`GET /api/v1/analyses/{analysis_id}`

- 成功返回 `200 OK` 和 `AnalysisTask`。
- `RUNNING` 时 `result` 与 `error` 均为 `null`。
- `SUCCEEDED`、`PARTIAL` 时 `result` 非空，且只包含核验后的结果。
- `FAILED` 时 `result` 为 `null`，`error` 非空。
- `CANCELLED` 时 `result` 与 `error` 均为 `null`。

### 4.4 取消分析任务

`POST /api/v1/analyses/{analysis_id}/cancel`

- 尚未开始或可中断时返回 `200 OK`，状态为 `CANCELLED`。
- 已进入终态时返回当前任务，不回滚结果。
- 底层模型调用无法安全中断时，服务仍须丢弃迟到结果，不能把任务重新改成成功。

### 4.5 获取原文页

`GET /api/v1/documents/{document_id}/pages/{page}`

```json
{
  "document_id": "housing-policy-a13f40c26df1a170",
  "page": 2,
  "text": "第五条 补贴标准……",
  "fragments": [
    {
      "fragment_id": "housing-policy-a13f40c26df1a170-p2-c0",
      "document_id": "housing-policy-a13f40c26df1a170",
      "page": 2,
      "text": "第五条 补贴标准……"
    }
  ]
}
```

页码小于 1 或超过 `page_count` 返回 `404 PAGE_NOT_FOUND`。响应只包含指定页，不默认返回完整文档。

## 5. HTTP 状态码

| HTTP | 使用场景 |
|---:|---|
| 200 | 查询、取消或幂等重放成功 |
| 201 | 文档上传并解析成功 |
| 202 | 分析任务已接受 |
| 400 | 请求字段或状态不合法 |
| 404 | 文档、页面或任务不存在 |
| 409 | 幂等键与不同请求冲突 |
| 413 | 文件超过 20 MiB |
| 415 | 文件类型不支持 |
| 422 | 文件损坏、为空或无可提取文本 |
| 429 | 模型额度或服务限流 |
| 500 | 未分类的内部错误 |
| 502 | 模型输出无法解析或上游返回无效响应 |
| 503 | 模型服务暂时不可用 |
| 504 | 模型调用超时 |

## 6. 稳定错误代码

| `code` | HTTP | 可重试 | 含义 |
|---|---:|:---:|---|
| `INVALID_REQUEST` | 400 | 否 | 请求字段不符合契约 |
| `IDEMPOTENCY_CONFLICT` | 409 | 否 | 同一幂等键对应不同请求 |
| `FILE_TOO_LARGE` | 413 | 否 | 超过 20 MiB |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 否 | 不支持的文件类型 |
| `EMPTY_FILE` | 422 | 否 | 文件为空 |
| `DOCUMENT_DAMAGED` | 422 | 视情况 | 文件无法解析 |
| `NO_EXTRACTABLE_TEXT` | 422 | 否 | 文件没有文本层且 OCR 未启用 |
| `DOCUMENT_NOT_FOUND` | 404 | 否 | 文档不存在或不可访问 |
| `PAGE_NOT_FOUND` | 404 | 否 | 页码不存在 |
| `ANALYSIS_NOT_FOUND` | 404 | 否 | 分析任务不存在 |
| `DOCUMENT_MISMATCH` | 500 | 否 | 分析结果与源文档不一致，结果已阻断 |
| `MODEL_UNAVAILABLE` | 503 | 是 | 模型服务或凭证不可用 |
| `MODEL_RATE_LIMITED` | 429 | 是 | 模型额度或速率受限 |
| `MODEL_TIMEOUT` | 504 | 是 | 模型调用超过服务端上限 |
| `MODEL_REFUSED` | 422 | 否 | 模型拒绝处理该请求 |
| `MODEL_OUTPUT_INVALID` | 502 | 是 | 模型响应不符合结构约定 |
| `ANALYSIS_FAILED` | 500 | 视情况 | 其他已捕获的分析失败 |

`message` 面向用户，不包含堆栈、密钥、内部路径或原始模型响应；详细诊断只进入经过脱敏的服务端日志。

单个分析任务的服务端上限为 120 秒。模型客户端在首次调用后最多重试 2 次（含首次最多 3 次尝试），最后一次改用 `deepseek-v4-pro`；SDK 自带重试关闭，避免突破总量。连接中断、超时、限流、明确的临时上游错误、空内容截断和结构解析失败可以在该上限内重试；拒答、鉴权失败与请求不合法不得重试。取消或超时后即使上游迟到返回，也必须丢弃结果。

## 7. 首版安全与部署边界

- v0.1 不提供账号、认证或租户模型，因此只允许绑定本机回环地址或运行在等价的单用户隔离环境。
- 若部署到局域网、公网或多用户环境，发布必须被阻断，直到接口增加认证、资源所有权校验、存储隔离和访问审计，并通过 T10。
- 上传内容的保存周期和删除策略由 A 在部署方案中确定；在此之前，不得声称文件会自动删除。
- 当前任务、文档与幂等键只保存在服务进程内；进程重启后不会保留，不能宣称跨重启幂等或持久化。
- 当前哈希链可发现链内记录的部分修改，不能证明日志未被整体替换或截断。

## 8. P05 评审清单

- A：确认 20 MiB 限制、单机部署边界、幂等保留时间以及 HTTP 框架和持久化方案。
- D：确认所有页面状态均能映射到 `AnalysisTask.state`、错误对象和引用对象。
- E：确认 T01–T12 能从本契约获得可观察结果，特别是 T04、T07、T09、T10。
- C：评审通过后登记契约版本；后续字段或语义变更先修改本文，再改实现。
