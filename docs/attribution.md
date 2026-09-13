# 开源归属与团队贡献说明（P12 · B-10）

依据：[00-项目文档/00-团队项目0号文档.md](../00-项目文档/00-团队项目0号文档.md) §13.2 最终交付清单（"开源归属说明"）；[00-项目文档/01-五人分工与任务清单.md](../00-项目文档/01-五人分工与任务清单.md) B-10。

负责人：B（署名 yang660op）｜执行日期：2026年9月13日｜复核人：A（技术统筹）、项目负责人｜待复核状态

本文交付两块：

- §1 **第三方依赖归属**：直接依赖与可选依赖的名称、版本、许可证、用途。
- §2 **团队贡献分工**：谁在哪个提交范围里做了什么，本轮 B 的具体贡献。

---

## 一 第三方依赖归属

### 1.1 运行时直接依赖（`pyproject.toml` 主 `dependencies`）

| 名称 | 版本 | 许可证 | 用途 | 归属 |
|---|---|---|---|---|
| anthropic | 1.4.0 | MIT | Claude 模型调用 SDK；`reasoner.py` 使用其 `messages.create` 与结构化输出 | Anthropic PBC，https://github.com/anthropics/anthropic-sdk-python |
| pypdf | 6.18.0 | BSD-3-Clause | 文本层 PDF 抽取；`parsers._load_pdf_pypdf` 使用 | py-pdf 组织，https://github.com/py-pdf/pypdf |

### 1.2 可选依赖

| 名称 | 版本 | 许可证 | 用途 | 归属 | 本轮启用 |
|---|---|---|---|---|---|
| docling | 2.126.0 | MIT | 富文档解析（DOCX / PPTX / 图片 / 表格 / OCR）；`parsers._load_with_docling` | IBM Research，https://github.com/DS4SD/docling | 未启用 |
| browser-use | 0.13.10 | MIT | 浏览器自动化执行；未来接入 `actions.py` 的执行器 | Browser Use，https://github.com/browser-use/browser-use | 未启用 |
| pytest | 9.1.1 | MIT | 测试框架 | pytest-dev | 启用（dev） |
| pytest-cov | 7.1.0 | MIT | 覆盖率插件 | pytest-dev | 启用（dev） |

### 1.3 传递依赖

以上依赖会引入若干传递依赖（如 anthropic 会引入 `httpx`、`pydantic`；pypdf 无强传递依赖）。传递依赖的清单以 `pip install -e ".[dev]"` 后 `pip list` 的实际输出为准，由 A 在 P11 部署阶段冻结。本文档不重复枚举，避免与实际 lockfile 不一致。

### 1.4 未使用但曾被评估过的组件

按 0 号文件 §二第三段规定：**先前给出的精确评分缺乏完整采集和计算证据，本方案不采用这些分数作为选型结论。** 若后续新增依赖，A 在 `docs/decisions.md` 记录选型理由。

### 1.5 数据素材归属

| 素材 | 位置 | 归属 |
|---|---|---|
| `examples/policy.txt` | 本仓库 | 团队原创的**虚构示例政策**（"市人才安居租房补贴实施细则（试行）"）；仅用于演示，不对应任何真实城市政策文本；如与真实政策雷同为巧合 |

**声明**：本项目当前**未使用**任何来自外部真实政策 PDF 或政务网页的素材。若后续引入真实政策样本，须按 0 号文件 §十二"使用真实材料前明确授权、存储和清理方式"处理，脱敏后入库。

### 1.6 模型服务归属

- **Claude 模型（`claude-opus-5` 系配置值）**：由 Anthropic 提供的商业 API。本轮未做过任何真实调用；`docs/baseline.md` §4.1 已声明。
- **凭证获取方式**：`ANTHROPIC_API_KEY` 环境变量或 `ant auth login`。凭证不入库。

---

## 二 团队贡献分工

### 2.1 责任线（引 [01-五人分工与任务清单.md](../00-项目文档/01-五人分工与任务清单.md) §三）

| 代号 | 责任线 | 主责工作包 |
|---|---|---|
| A | 仓库管理员 · 技术统筹 · 集成发布 | P01 · P05 共签 · P08 · P11 |
| B | 产品与调研 · 演示路演 | P02 · P03 · P12 |
| C | 后端与模型 | P05 · P06 · P10（后端） |
| D | 前端与交互 | P04 · P07 · P10（前端） |
| E | 测试与质量 | P09 |

**真实姓名**：项目卡未补齐前保留代号；成员名单确认后，本表由 A 全局替换。

### 2.2 本轮 B 的具体贡献

以下文件由 B 在 2026年9月13日创建，署名 `yang660op`：

| 文件 | 工作包 | 说明 |
|---|---|---|
| [TODO-B.md](../TODO-B.md) | — | 本轮 B 的工作跟踪表 |
| [docs/research.md](research.md) | P02（B-1 · B-2 · B-3） | 赛题官方规则未取得项标注 + 用户访谈未完成说明 + 三类替代方案走查 |
| [docs/product.md](product.md) | P03（B-4） | MVP 场景与功能边界 v1 |
| [docs/acceptance-set.md](acceptance-set.md) | P03（B-5 · B-6） | 24 条验收用例 + T01–T12 覆盖表 + 期望答案标注 |
| [docs/demo.md](demo.md) | P12（B-7 · B-8 · B-9） | 3 分钟演示脚本 + 备份录屏指引 + 排练检查清单 |
| [docs/attribution.md](attribution.md) | P12（B-10） | 本文 |

### 2.3 未变更的现有资产

本轮 B **未修改**任何运行时代码、测试文件、依赖声明或 CI 配置。以下资产维持在提交 `c3f723a` 的状态（引 `docs/baseline.md` §一）：

- `src/proofpath/` 全部源码
- `tests/` 全部测试
- `pyproject.toml`
- `.github/workflows/`（由 A 管理）
- `docs/decisions.md`（由 A 维护）
- `docs/baseline.md`（由 A / E 维护）
- `README.md`、`.gitignore`、`.gitattributes`

### 2.4 B 交付的验收依据

按 0 号文件 §9.1：**成果已纳入目标版本、相关检查通过、限制已记录、他人能依据说明复现**。

| 检查项 | 结果 |
|---|---|
| 成果已纳入目标版本 | 五份文档已在 `docs/B-P02-P03-P12` 分支的提交中 |
| 相关检查通过 | `pytest` 132 项通过；覆盖率 90%（引 §三） |
| 限制已记录 | 未取得的赛题信息、未完成的用户访谈、未启用的可选依赖均已在对应文档明示 |
| 他人能复现 | 每份文档均标注依据、日期、执行方式；`docs/acceptance-set.md` 用例含**输入 + 期望**，E 可按行执行 |

### 2.5 交付前的最后一轮测试

本轮 B 交付前跑一次 `pytest`，结果应与 `docs/baseline.md` §2.1 一致（132 项通过）。执行记录在 `docs/attribution.md` §三。

---

## 三 交付前测试记录

**执行日期**：2026年9月13日
**执行命令**：`python -m pytest -q --cov --cov-report=term`
**执行环境**：Windows 11 · Python 3.11.9（临时 venv：`%TEMP%\dsh-*\proofpath-b-venv`）
**执行人**：B（yang660op）
**期望**：132 项全部通过（引 `docs/baseline.md` §2.1）

**实际结果**：

```
132 passed in 6.69s

Name                         Stmts   Miss  Cover
------------------------------------------------
src\proofpath\__init__.py        7      0   100%
src\proofpath\actions.py        90      0   100%
src\proofpath\audit.py          89      2    98%
src\proofpath\cli.py           158     27    83%
src\proofpath\config.py         12      0   100%
src\proofpath\demo.py           14      0   100%
src\proofpath\errors.py         18      0   100%
src\proofpath\models.py         80      0   100%
src\proofpath\parsers.py       106     43    59%
src\proofpath\reasoner.py       74     12    84%
src\proofpath\render.py         45      2    96%
src\proofpath\retrieval.py      64      0   100%
src\proofpath\text.py           31      0   100%
src\proofpath\verifier.py       65      1    98%
------------------------------------------------
TOTAL                          853     87    90%
```

**与 baseline 比对**：132 项通过、总覆盖率 90%、分模块覆盖率**逐行一致**，未破坏基线。Python 版本比 `docs/baseline.md` 的 3.13.14 略低（3.11.9），是 `pyproject.toml` 声明的最低支持版本；结果一致说明代码路径与 3.13 上一致。

**依赖版本差异**：本次镜像装到 `anthropic==1.5.0`（`pyproject.toml` 钉在 `1.4.0`），`pypdf==6.18.1`（钉在 `6.18.0`）。原因是本机装 `.[dev]` 会超时，改用阿里镜像分开装时未显式钉版本。**本轮 B 只做文档，未改依赖声明**；A / E 在 P11 部署阶段应以 `pyproject.toml` 声明的版本为准。

若后续本地执行输出与基线不一致，B **不推送**分支，交由 A 排查。

---

## 四 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026年9月13日 | 创建 v1 | 直接依赖、可选依赖、素材来源、模型服务四类归属；本轮 B 贡献清单 |
