# 凭证配置与分发（模型密钥）

依据：00-项目文档/00-团队项目0号文档.md 第十二章（共享密钥通过适当的凭据渠道分发，文档只写变量名和配置步骤）；docs/decisions.md D-012、D-013。

负责人：A（仓库管理员）｜更新日期：2026年9月13日

本文只写**变量名、取值方式和操作步骤**，不写任何密钥内容。截至本文更新，仓库中没有任何真实密钥。

---

## 一 三条硬规则

1. **密钥只存在于环境变量或密码管理器里**，不落进代码、测试夹具、截图、录屏和聊天记录。
2. **仓库只保留变量名与取值方式**（`.env.example`）；`.env` 已被 `.gitignore` 忽略。
3. **分发只走私聊或共享密码库**：禁止发到群聊、issue、PR 评论、演示截图；需要多人共用时用密码管理器的共享条目，而不是复制粘贴。

---

## 二 变量清单

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | 是 | 无 | DeepSeek 平台 API Key，模型调用的唯一凭据 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | OpenAI 兼容格式入口 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-flash` | 难例可切 `deepseek-v4-pro` |
| `PROOFPATH_HOST` / `PROOFPATH_PORT` | 否 | `127.0.0.1` / `8000` | 后端监听地址（P06 生效） |
| `PROOFPATH_MAX_UPLOAD_BYTES` | 否 | 20 MiB | 上传大小上限 |
| `PROOFPATH_ANALYZE_TIMEOUT_SECONDS` | 否 | 120 | 单次分析超时 |
| `ANTHROPIC_API_KEY` | 否 | 无 | 过渡期专用，P06 合并后删除 |

`PROOFPATH_*` 一组由 A 与 C 在 P05 契约评审中共同确认；如需改动，按 D-011 的变更流程记录一次。

---

## 三 本机配置步骤

1. 复制样例文件：把 `.env.example` 复制为 `.env`（同一目录，仓库根）。
2. 在 `.env` 中只填 `DEEPSEEK_API_KEY` 的值，其余保持默认。
3. 确认 `.env` 没有被 git 跟踪：`git status --short` 中**不应**出现 `.env`；出现即说明 `.gitignore` 被破坏，立刻停止并通知 A。
4. Windows PowerShell 若希望用系统环境变量而不是 `.env`：

```powershell
$env:DEEPSEEK_API_KEY = "<你的密钥>"   # 仅当前窗口有效
```

macOS / Linux：

```bash
export DEEPSEEK_API_KEY="<你的密钥>"
```

不要把上面两条命令连同真实密钥粘进任何文档、issue 或聊天窗口。

---

## 四 连通性自检

有密钥时，用一条命令确认密钥可用（返回模型列表即成功）：

```powershell
curl.exe -s https://api.deepseek.com/models -H "Authorization: Bearer $env:DEEPSEEK_API_KEY"
```

```bash
curl -s https://api.deepseek.com/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"
```

Python 侧等价写法（`openai` SDK 3.13.0 实测可连通）：

```python
from openai import OpenAI
client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
client.models.list()
```

**已完成的验证**：

1. 用无效密钥实测 `https://api.deepseek.com` 上的 `/models` 与 `/chat/completions`，均返回 `401 AuthenticationError`（OpenAI 风格错误体），证明入口地址与 SDK 接线正确。
2. 2026年9月13日用有效密钥完成真实调用（3 次，含一次端到端核验链路），结果与实现要求见 `docs/decisions.md` D-012。密钥由项目负责人提供，**未写入仓库、未写入任何文件**。

---

## 五 团队分发方式

| 场景 | 做法 |
|---|---|
| 成员首次获取 | 由项目负责人或 A 在 DeepSeek 平台创建密钥后，通过**密码管理器共享条目**或**一对一私聊**发出 |
| 演示现场 | 使用演示机上的本地 `.env` 或系统环境变量；演示前确认额度，且不要把密钥显示在屏幕上 |
| CI | 配置为 GitHub Repository secret，名称 `DEEPSEEK_API_KEY`；工作流只引用变量名，不得 echo 出值 |
| 多人调试 | 各自申请各自的密钥，便于按人计费与吊销；不共用同一把密钥 |

禁止清单：群聊发送、写入仓库文件、贴进 issue/PR、出现在截图或录屏里、写进 `examples/`、写进测试夹具。

---

## 六 轮换与泄露处置

**轮换**：每 30 天，或成员离开、密钥疑似外泄时立即更换。吊销在 DeepSeek 平台执行，不需要改动代码。

**只要密钥出现在聊天记录、群聊、截图、录屏或任何公开渠道，就按已泄露处理并立即轮换**——不要因为"只是发给同事"而放过。

**发现泄露时按顺序做五件事**：

1. 立刻在平台吊销该密钥（先止血，不要先调查）。
2. 生成新密钥并按第五节分发，确认服务恢复。
3. 检查仓库历史与 CI 日志是否留有该密钥；若已进入提交历史，通知 A 处理（需要重写历史时按 D-008 的规则评估）。
4. 在 `docs/decisions.md` 记录事件：时间、范围、原因、影响、处理动作。
5. 通知团队实际受影响的调用与费用，必要时核对账单。

---

## 七 费用控制

官方计价（每 100 万 token，2026年9月13日取自官方文档）：

| 模型 | 输入（缓存未命中） | 输出 |
|---|---|---|
| `deepseek-flash` | $0.15（谷时）/ $0.30（峰时） | $0.60 / $1.20 |
| `deepseek-v4-pro` | $0.66 / $1.32 | $1.98 / $3.96 |

峰时为周一至周五 `01:00–04:00` 与 `06:00–10:00` UTC（北京时间 09:00–12:00 与 14:00–18:00），其余时段按谷时计费。上下文缓存默认开启，重复前缀按缓存命中价计费。

**单次分析估算**（假定输入约 8k token、输出约 1.5k token）：`deepseek-flash` 约 $0.0021／次，`deepseek-v4-pro` 约 $0.0083／次；峰时翻倍。按 100 次测试算，flash 约 $0.2。

建议：在平台设置余额提醒；默认用 `deepseek-flash`，只在难例或失败重试时升级到 `deepseek-v4-pro`；把模型名做成可配置项，超预算时可以直接降级而不改代码。
