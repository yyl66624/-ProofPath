# 真实测试手册 — 怎么把 ProofPath 跑起来

> 本文档是 0 号文件 13 节 "Demo 与交付" 的具体操作版。覆盖「让用户从零启动整套项目并完成真实测试」所需的一切。

## 0. TL;DR

```bash
# 一次性安装（Python 3.11+）
uv venv --python 3.12
uv pip install -e ".[dev,server]"
(cd frontend && pnpm install)

# 一键起前后端（无凭证也能跑 — 后端自动 ScriptedReasoner）
bash scripts/dev.sh

# 浏览器打开
open http://127.0.0.1:5173
```

如果上面的命令成功，你已经能：
- 在前端 UI 上点 "使用演示样例" → 走完整四步向导（mock 数据，不依赖后端）
- 在前端 UI 上点 "真实接口" → 上传 `examples/policy.txt` → 看后端真实响应（demo 模式下走 ScriptedReasoner）
- 访问后端 Swagger UI 看 OpenAPI 文档
- 跑 `proofpath demo` CLI 演示

## 1. 先决条件

| 工具 | 最低版本 | 检测 | 备注 |
|---|---|---|---|
| Python | 3.11 | `python3 --version` | 3.12 推荐 |
| Node.js | 18 | `node --version` | 20 LTS 推荐 |
| pnpm | 8 | `pnpm --version` | 必需（frontend 锁文件） |
| uv | 0.4+ | `uv --version` | 推荐；也可用 `pip` 替代 |

如果没装 pnpm：`npm install -g pnpm` 或 `corepack enable && corepack prepare pnpm@latest --activate`

## 2. 安装

### Python 后端

```bash
# 在仓库根目录
uv venv --python 3.12
uv pip install -e ".[dev,server]"

# 验证
PYTHONPATH=src .venv/bin/python -m proofpath --version
# → proofpath 0.1.0
```

`server` 额外依赖（fastapi / uvicorn / openai / python-multipart / httpx2）必须在，否则后端跑不起来。

### 前端

```bash
cd frontend
pnpm install
pnpm exec -- tsc -b    # 可选 — 验证类型
cd ..
```

`pnpm-workspace.yaml` 已经允许 esbuild postinstall，所以装完即可直接用。

### 可选依赖

```bash
uv pip install -e ".[docling]"   # 扫描件 OCR、DOCX/PPTX/图片解析
uv pip install -e ".[browser]"   # 浏览器自动填表（需额外 playwright install chromium）
```

## 3. 启动（三种方式）

### 方式 A：一键脚本（推荐）

```bash
bash scripts/dev.sh
```

行为：
- 后端 `127.0.0.1:8000`，前端 `127.0.0.1:5173`
- **若 `DEEPSEEK_API_KEY` 未设置**：后端自动用 `ScriptedReasoner`（D-014 demo 模式），上传/分析/证据核验照样工作
- **若设置了** `DEEPSEEK_API_KEY=sk-...`：用真实 DeepSeek 模型
- 按 Ctrl-C 同时关闭两端

### 方式 B：分两个终端（看实时日志更清楚）

```bash
# 终端 1：后端
PYTHONPATH=src .venv/bin/python -m uvicorn proofpath.api:app --host 127.0.0.1 --port 8000

# 终端 2：前端
cd frontend && pnpm dev --host 127.0.0.1 --port 5173
```

### 方式 C：只起后端（用 curl 测 API）

```bash
# 起服务
PYTHONPATH=src .venv/bin/python -m uvicorn proofpath.api:app --host 127.0.0.1 --port 8000

# 另一终端测试
curl http://127.0.0.1:8000/docs                              # Swagger UI
curl -X POST http://127.0.0.1:8000/api/v1/documents \
     -F "file=@examples/policy.txt"                           # 上传
# 返回 {"document_id": "source-...", "page_count": 2, ...}
```

## 4. 测试场景

### 4.1 离线 CLI 演示

```bash
PYTHONPATH=src .venv/bin/python -m proofpath demo --audit run.jsonl
PYTHONPATH=src .venv/bin/python -m proofpath audit run.jsonl
```

预期：6 条逐条判定，其中 2 条因引用无法核验被强制降级为"原文未明确"——这就是 README 强调的"信任边界"。

### 4.2 前端 UI — 演示样例模式

1. 浏览器打开 `http://127.0.0.1:5173`
2. 页面右上角确认在 "演示样例" 模式（橙色选中态）
3. 点 "使用演示样例" 按钮 → 直接进资料补充页
4. 填几个必填字段（学历、年龄、社保）→ "继续"
5. 在分析页看 6 条判定，**注意 2 条 "原文未明确"**（这正是埋设的拦截演示）
6. 第四步看原文与定位

整个流程**不依赖后端**——是前端 mock 数据。

### 4.3 前端 UI — 真实接口模式

1. 页面右上角切到 "真实接口" 模式（蓝色选中态）
2. 回到步骤 1，**点 "选择文件"** 选 `examples/policy.txt`
3. 在问题框输入：`我硕士28岁能申请吗`
4. 点 "上传并继续" → 进资料补充页
5. 填几个字段 → 继续
6. 在分析页看后端真实响应
7. 第四步可点引用跳到原文页（后端 `/api/v1/documents/{id}/pages/{n}`）

**注意**：在 demo 模式下（无 DEEPSEEK_API_KEY），你会看到 6 条判定与 CLI 演示完全一致——因为后端用了 ScriptedReasoner。但数据流是真实的（HTTP → FastAPI → service → reasoner → verifier → 渲染）。

### 4.4 后端 API 端到端

最小冒烟测试（用 curl）：

```bash
# 1. 上传
DOC_ID=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/documents \
  -F "file=@examples/policy.txt" | jq -r .document_id)
echo "DOC_ID=$DOC_ID"

# 2. 创建分析（注意 Idempotency-Key 必须 16-128 字符）
RESP=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/analyses \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: smoke-$(date +%s)-test-001" \
  -d "{\"document_id\":\"$DOC_ID\",\"question\":\"我硕士能申请吗\",\"profile\":[{\"key\":\"学历\",\"value\":\"硕士\",\"state\":\"PROVIDED\",\"source\":\"USER_INPUT\"}]}")
AID=$(echo "$RESP" | jq -r .analysis_id)
echo "AID=$AID"

# 3. 查询（可能仍 RUNNING，等 1 秒再查）
sleep 1
curl -sS "http://127.0.0.1:8000/api/v1/analyses/$AID" | jq .
```

预期：最终 `state` = `PARTIAL`（因有 MET/UNMET，trust boundary 标记需要人工复核），`result.verdicts` 有 6 条，`result.materials` 是材料清单。

### 4.5 审计链

```bash
PYTHONPATH=src .venv/bin/python -m proofpath demo --audit run.jsonl
PYTHONPATH=src .venv/bin/python -m proofpath audit run.jsonl
# → 审计链校验通过:2 条记录
```

篡改一行再验：

```bash
echo '{"mutated": true}' >> run.jsonl
PYTHONPATH=src .venv/bin/python -m proofpath audit run.jsonl
# → 审计链校验失败: ...（应明确指出断裂位置）
```

恢复：

```bash
rm run.jsonl
```

## 5. 常见问题

### 5.1 `pnpm install` 卡住 / 报 ECONNREFUSED

`127.0.0.1:8890` 代理不可达。本仓库的 `~/.npmrc` 和 `~/.gitconfig` 默认指向这个代理，但本环境它没起。

绕过：

```bash
mv ~/.npmrc ~/.npmrc.bak     # 临时备份
(cd frontend && pnpm install)
mv ~/.npmrc.bak ~/.npmrc     # 恢复
```

或者（不推荐改用户配置）：

```bash
pip config set global.proxy ""   # Python 侧
# pnpm 侧：用本仓库的 .npmrc 已配 ignore-scripts=true + pnpm-workspace.yaml 的 allowBuilds
```

### 5.2 `proofpath check` 报 `MODEL_UNAVAILABLE`

正常。`check` 需要真实 DeepSeek API 凭证：

```bash
export DEEPSEEK_API_KEY=sk-...      # 从 https://platform.deepseek.com/ 申请
# 然后重启后端，让它检测到环境变量并切到真实 reasoner
```

或先用 `proofpath demo` 体验完整流程（无需凭证）。

### 5.3 前端点 "真实接口" 上传后报 400 / 404

最常见：浏览器未通过 vite proxy 转发。检查：

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/api/v1/documents
# 期望 405（GET 不支持）或 422（缺文件） — 说明 proxy 通了
# 若 404 → proxy 没配；查 vite.config.ts
```

### 5.4 端口冲突

后端改 `PROOFPATH_PORT=8001`（并相应改 `vite.config.ts` 的 proxy target）。前端 vite 改 `pnpm dev --port 5174`。

### 5.5 测试集失败

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
# 看哪个文件失败，单跑：
PYTHONPATH=src .venv/bin/python -m pytest tests/test_verifier.py -v
```

如果 `ImportError: No module named 'fastapi'`：重装 `uv pip install -e ".[server]"`。

## 6. 端口与配置

| 端口 | 服务 | 环境变量 / 配置 |
|---|---|---|
| 8000 | 后端 FastAPI | `PROOFPATH_PORT`；OpenAPI `/docs` |
| 5173 | 前端 Vite | `vite.config.ts` 的 `server.port` |
| (后端 → 前端) | Vite proxy `/api/*` → `127.0.0.1:8000` | `vite.config.ts` 的 `server.proxy` |

后端启动参数：

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `DEEPSEEK_API_KEY` | (无) | 缺省 → ScriptedReasoner demo 模式 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 入口 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 可改 `deepseek-v4-pro` |
| `PROOFPATH_HOST` | `127.0.0.1` | 服务监听地址 |
| `PROOFPATH_PORT` | `8000` | 端口 |
| `PROOFPATH_MAX_UPLOAD_BYTES` | `20971520` | 上传上限 (20 MiB) |
| `PROOFPATH_ANALYZE_TIMEOUT_SECONDS` | `120` | 单次分析超时 |

## 7. 已知边界

（与 0 号文件 9.4 + README "已知边界" 一致）

- **不是最终资格认定**。所有结果带"以受理窗口答复为准"提示。
- **演示模式用固定剧本**。`ScriptedReasoner` 总是返回同一份 6 条报告（其中 2 条埋设了"原文未明确"），用于演示"系统能在模型出错时兜住"——但不是真实模型分析。
- **检索为词面匹配 (BM25)**。用户用词与原文接近时好用，完全同义改写可能搜不到——会拒答而非编造。
- **浏览器执行器尚未接入**。`proofpath plan` 只做风险分级演练，不实际执行。
- **没做演示模式下的真实流程**——demo 模式的数据是 mock 的；要让"演示样例"也走真实 API 链路，只需把后端设上 `DEEPSEEK_API_KEY`，前端切到"真实接口"。

## 8. 一图看流程

```
  ┌─────────────────┐   uploadDocument    ┌──────────────────┐
  │  Browser (5173) │ ──────────────────▶ │  FastAPI (8000)  │
  │   React+TS UI   │ ◀────────────────── │   /api/v1/...    │
  └─────────────────┘   JSON + Idem-Key   └──────────────────┘
         │                                        │
         │ /api/* via vite proxy                  │ if DEEPSEEK_API_KEY:
         │                                        │   → DeepSeekReasoner
         │                                        │ else:
         │                                        │   → ScriptedReasoner
         │                                        ▼
         │                                 ┌──────────────┐
         │                                 │  service.py  │
         │                                 │  → verifier  │
         │                                 │  → render    │
         │                                 └──────────────┘
         ▼
  ┌──────────────────┐
  │ proofpath CLI    │   (无 UI，命令行)
  │  demo/parse/...  │
  └──────────────────┘
```
