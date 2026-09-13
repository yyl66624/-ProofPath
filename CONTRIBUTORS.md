# Contributors

按 `git shortlog -sn --no-merges --all` 统计，合并 commit 不计入。下表统计范围：截至 `1818d75`（合并完所有 9 个远端分支 + integration/P09-quality-review 之后的 main HEAD）之前的全部 non-merge commit。

## A. 有独立 git commit 的贡献者

| Author | Commits | 主要贡献 |
|---|--:|---|
| [@yyl66624](https://github.com/yyl66624) | 17 | 仓库主；CI / 治理基线 / 决策记录 D-002–D-013 / P09 验收与质量整合 / 前端 P04-P10 / E 角色冻结标准 |
| [@yang660op](https://github.com/yang660op) | 2 | B 角色（产品与调研）：P02 + P03 + P12 交付 — 调研记录 / MVP 边界 / 24 例验收集 / 演示 / 归属 |
| [@joyboy](https://github.com/joyboy1345) | 1 | P05/P06 后端：DeepSeek reasoner + FastAPI 服务层（`api.py` / `api_schemas.py` / `service.py`） |

未计入的合并署名（agent 合并时使用的 bot 身份，不算真人）：

- `ProofPath-CI <ci@proofpath.local>` — 4 条独立 commit，全是 0 号文件 D-014 范围内的工作（合并 9 个远端分支 + E 角色测试修复 + 前端构建修复 + 决策记录）。

## B. 项目负责人确认的协作者（无独立 git commit 记录）

下列两位经项目负责人 `yyl66624` 在 2026-09-14 会诊中口头确认参与了仓库工作。**说明：截至本文件最后一次更新，git 层面（author / committer / co-author / signed-off-by / reflog / commit message）均未检索到这两位的记录**；GitHub web UI 的 `branches` 页面在 `feat/d-frontend-p04-p07-p10` 和 `test/E-quality-P09` 这两个 active branch 上显示的 "Updated by" 头像**不是 yyl66624**（参见用户提供的截图），表明有人 push 了这两个分支——基于项目负责人确认，推送者即以下两人，但**无独立 git commit**：

| 协作者 | 经项目负责人确认的活动 | 可核验的间接证据 |
|---|---|---|
| **zhangdsg** | 经 yyl66624 确认参与了 `feat/d-frontend-p04-p07-p10` 与（或）`test/E-quality-P09` 两个分支的工作 | GitHub web UI 截图显示这两个 active branch 的 "Updated by" 头像不是 yyl66624；具体分工由项目负责人声明 |
| **luckymood** | 经 yyl66624 确认参与了 `feat/d-frontend-p04-p07-p10` 与（或）`test/E-quality-P09` 两个分支的工作 | 同上 |

> **诚实声明**：这两人不满足通常意义上的"git 贡献者"判据（独立 commit、co-author、signed-off-by）。他们被列入是因为项目负责人对他们的参与做了明确确认；外部评审/审计如果要核实"做了什么"，请以项目负责人的书面/口头确认为准，**不要**仅凭此文件去推断他们的实际技术贡献范围。
>
> 这条诚实声明是为了避免下游误用——例如有团队误以为这两人写了某段代码，然后去联系他们修 bug，结果发现他们其实没写过。

---

## 角色 / 任务包对应（来自 00-项目文档）

0 号文件按 A/B/C/D/E 五条责任线组织工作；上面 5 位是项目负责人认可的贡献者。每个工作包的 P 编号（[00-项目文档/01-五人分工与任务清单.md](00-项目文档/01-五人分工与任务清单.md) 中的 A-1 / B-5 / C-12 等）可在 git log 里反查到对应 commit（注意：仅 A/B/C 表中的 3 位可在 git log 反查；D/E 表中的 zhangdsg / luckymood 不在 git log 内）。

| 角色代号 | 真实贡献者 | 主要工作包 | git 可核验 |
|---|---|---|:--:|
| A（技术统筹 / 集成） | yyl66624 | P00 项目卡 / P01 资产盘点 / G0–G2 治理 / 决策记录 / CI 落地 | ✓ |
| B（产品 / 调研 / 演示） | yang660op | P02 调研 / P03 MVP / P12 演示与归属 | ✓ |
| C（后端 / 模型） | joyboy | P05 后端基础 / P06 DeepSeek 推理 | ✓ |
| D（前端） | yyl66624（git 提交）+ zhangdsg / luckymood（经确认参与 push） | P04 流程 / P05 契约 / P07 实现 / P10 受控填表 | 部分 |
| E（测试 / 质量） | yyl66624（git 提交）+ zhangdsg / luckymood（经确认参与 push） | P09 质量评估 / 冻结验收标准 | 部分 |
| 项目负责人 + Codex | yyl66624（兼） | 0 号文件第四节 | ✓ |

> 注：A/D/E 由 yyl66624 兼任是项目实际人员配置（00-项目文档第四节"两人团队：负责人兼产品、前端和演示；另一位负责后端与集成，Codex 协助各环节"），不是重复计入。`ProofPath-CI` 是 agent 合并时的 git author 身份，不计为真人贡献者。

---

## 提交贡献之外

下列工作未直接产生 git commit，但出现在仓库的 `00-项目文档/`、`docs/decisions.md`、PR 描述与 issue 记录中：

- **项目负责人**（匿名为 0 号文件第四节角色）—— 赛题、目标用户、优先级、预算与最终验收；与 D-001 / D-007 / D-008 等决策绑定。
- **Codex（技术统筹 agent）** —— 拆解任务、接口协调、集成、文档维护（0 号文件第四节职责），本次 0 号文件与本次会诊中的 P00–P12 工作包整理。

如要把这些身份也列入，请在此文件直接追加，并提供可核验的引用（commit、PR、issue 或决策记录编号）；不要列入没有任何可核验痕迹的成员。

---

最后更新：与 main `1818d75` 同步；2026-09-14 增补"项目负责人确认的协作者"小节（zhangdsg / luckymood），证据等级与诚实声明已显式标注。
