# 运行基线复验记录（P01）

依据：00-项目文档/00-团队项目0号文档.md 第二章、第十一章 P01；00-项目文档/01-五人分工与任务清单.md 第二节与 A-7。

负责人：A（仓库管理员）｜执行日期：2026年9月13日｜复核人：E（待复核，尚未执行）

本文只记录**实际执行出来的结果**。任何未在本文件中出现的数字，都不应作为本项目的验收证据。

---

## 一 复验环境

| 项目 | 值 |
|---|---|
| 操作系统 | Windows 11（Windows-11-10.0.26200-SP0） |
| Python | 3.13.14（MSC v.1944 64-bit） |
| 虚拟环境 | 新建独立环境 `%TEMP%\proofpath-baseline-venv`（仓库外），用于验证"从零能否跑通" |
| 安装命令 | `python -m pip install -e ".[dev]"` |
| 关键依赖 | anthropic 1.4.0、pypdf 6.18.0、pytest 9.1.1、pytest-cov 7.1.0、coverage 7.16.0 |
| 代码版本 | 提交 c3f723a（本次治理提交未改动任何运行时代码） |
| 可选依赖 | docling 未安装、browser-use 未安装（见第四节） |

未在 Windows 之外的平台验证，也未验证 Python 3.11／3.12；这两项由 CI 覆盖，见 `docs/decisions.md` D-006。

---

## 二 实际执行结果

### 2.1 测试

```
$ python -m pytest -q
132 passed in 1.23s
```

### 2.2 覆盖率

```
$ python -m pytest -q --cov --cov-report=term

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
132 passed in 2.25s
```

覆盖率只用于发现测试空白，不设统一百分比门槛（0 号文件 9.4）。目前最薄的两处是 `parsers.py`（59%，docling 分支未覆盖）与 `cli.py`（83%）。

### 2.3 离线演示链路的拦截效果

```
$ python -m proofpath.cli demo
...
## 证据核验
引用 7 处：已核验 5，基本一致 0，未通过 2
有 2 条结论因引用无法核验，已降级为“原文未明确”。
本结果不是最终资格认定，请以受理窗口的答复为准。
```

两处被拦下的缺陷与设计预期一致：

1. 第 4 条结论（补贴标准 + 追补 3 个月）中，一条引用真实可定位，另一条“首次申请的人员可以追补此前3个月的补贴”在原文中不存在（覆盖率 11%），**整条结论被降级**。这正是“复合结论中夹带一句编造”的拦截点。
2. 第 5 条结论的引用只有两个字“合同”，被判定为引用过短、不足为证，**结论降级**。

### 2.4 敏感操作闸门

```
$ python -m proofpath.cli plan "https://example.gov.cn/apply"
执行计划:
  1. [READ_ONLY  ] 可自动  navigate -> https://example.gov.cn/apply
  2. [LOCAL_WRITE] 可自动  fill -> 申请人姓名
  3. [LOCAL_WRITE] 可自动  fill -> 身份证号
  4. [SENSITIVE  ] 需确认  upload -> 学历学位证书
  5. [SENSITIVE  ] 需确认  submit -> 提交申请

风险统计: {'READ_ONLY': 1, 'LOCAL_WRITE': 2, 'SENSITIVE': 2}
已在敏感操作前停止: action 'upload -> 学历学位证书' is SENSITIVE and requires explicit user confirmation

plan exit=3
```

退出码 3 表示“已在敏感操作前停止”，不是失败。

### 2.5 解析与检索

```
$ python -m proofpath.cli parse examples/policy.txt
第 1 页 (390 字): 市人才安居租房补贴实施细则(试行) ...
第 2 页 (512 字): 第三章 补贴标准 ...
已解析 policy.txt(解析器 plaintext,2 页,2 个片段)

$ python -m proofpath.cli search examples/policy.txt -q "硕士 补贴标准 每月"
1. [第 2 页] score=9.106   （命中补贴标准条款）
2. [第 1 页] score=1.490   （命中总则）
```

### 2.6 可选组件状态

```
$ python -m proofpath.cli doctor
ProofPath 0.1.0
默认模型: claude-opus-5
  [可用    ] pypdf (PDF 解析)
  [未安装   ] docling (DOCX/图片/OCR)
  [未安装   ] browser-use (表单自动填写)
  [可用    ] anthropic (模型调用)
```

### 2.7 新增依赖验证（同日追加，对应 D-009、D-012）

在**另一个全新的独立 venv**中执行 `python -m pip install -e ".[dev,server]"`，验证新增依赖从零可安装、且不影响既有测试：

```
$ python -m pip check
No broken requirements found.

$ python -m pytest -q
132 passed in 30.64s
```

新增依赖版本：fastapi 0.141.1、uvicorn 0.52.4、python-multipart 0.0.32、openai 3.13.0。DeepSeek 入口接线另用无效密钥实测：`https://api.deepseek.com/models` 与 `/chat/completions` 均返回 `401 AuthenticationError`（OpenAI 风格错误体），证明 base_url 与 SDK 接线正确。

**仍未验证**：真实模型调用（无有效密钥）、Linux 与 Python 3.11（由 CI 覆盖）。

---

## 三 与既有基线的比对

| 指标 | 01 号文档第二节 | 本次复验 | 结论 |
|---|---|---|---|
| 测试数量 | 132 通过 | 132 通过 | 一致 |
| 总覆盖率 | 90% | 90% | 一致 |
| 分模块覆盖率 | verifier 98%、actions/models/retrieval/text 100% | 同上 | 一致 |
| 离线链路拦截 | 2 处缺陷被拦下 | 逐条一致 | 一致 |
| 动作闸门 | 敏感操作前停止，退出码 3 | 同上 | 一致 |
| 裸环境 | 124 通过 / 8 失败（缺 anthropic、pypdf） | 本次改以“新建干净 venv 后按声明依赖安装”验证 | 该项结论仍来自 9月13日系统 Python 环境 |

---

## 四 本次未验证的事项

1. **真实模型链路**：没有任何一次 `proofpath check` 的真实调用记录，`ANTHROPIC_API_KEY` 与 `ant auth login` 都未使用。模型名 `claude-opus-5`、回退参数、思考与结构化输出配置全部属于**未验证声明**。
2. **Linux 与 Python 3.11／3.12**：本地只有 Windows + 3.13。CI 工作流已写好，首次运行结果出来前不得声称跨平台可用。
3. **docling 与 browser-use**：两个可选组件均未安装，对应代码路径（扫描件 OCR、DOCX／图片解析、真实浏览器执行）从未运行过。`parsers.py` 覆盖率 59% 正对应这里。
4. **T04“引用真实但不支持结论”**：核验模块只检查引用能否定位，不检查引用是否支撑结论，当前没有对应实现与用例。
5. **服务化能力**：仓库没有任何 HTTP 接口、前端页面或任务状态机，P04–P07 尚未开始。
