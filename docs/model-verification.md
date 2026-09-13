# 模型接线与行为验证记录（DeepSeek）

依据：`docs/decisions.md` D-012；00-项目文档/00-团队项目0号文档.md 9.2（运行检查）、9.4（Demo 发布条件）。

执行人：A（仓库管理员）｜执行日期：2026年9月13日｜复核人：C（P06 实现）、E（P09 评估）

**本文记录的是接线与行为验证，不是模型质量评估。** 3 次调用、1 份文档、1 个问题，不满足 9.4 要求的 20 例规模；质量评估由 E 在 P09 执行，本文只提供输入。

本文不记录任何密钥值，也不记录密钥指纹。密钥由项目负责人提供，仅通过环境变量传入。

---

## 一 目的

在 C 落地 P06 之前，用真实密钥确认三件事：

1. 入口地址、SDK 与鉴权接线是否正确；
2. 思考模式与 `max_tokens` 的交互会不会造成静默失败；
3. 模型输出能否通过项目**已有的逐字核验**（`verify_report`）。

---

## 二 环境与方法

| 项目 | 值 |
|---|---|
| 客户端 | `openai` SDK 3.13.0，`base_url="https://api.deepseek.com"` |
| 鉴权 | 密钥从环境变量 `DEEPSEEK_API_KEY` 读取，不落盘、不入库 |
| 复用模块 | `load_document`、`Bm25Index`、`build_context`、`SYSTEM_PROMPT`、`_build_user_prompt`、`_parse_payload`、`verify_report` |
| 文档 | `examples/policy.txt`（2 页，2 个片段） |
| 问题与资料 | 与离线 demo 相同的申报场景 |
| 输出约束 | `response_format={"type": "json_object"}`，并在提示词中补充 JSON 字段说明（DeepSeek 要求提示词中出现 json 字样） |

---

## 三 实验一：思考模式与 max_tokens 的交互

先用一句小提示词做探针（`max_tokens=16`）：

| 配置 | 正文 | 推理文本长度 | token（入/出） | finish_reason |
|---|---|---|---|---|
| 思考默认 | **空** | 72 字符 | 34 / 16 | `length` |
| 关闭思考 | 正常 | 0 | 8 / 1 | `stop` |
| 思考默认，max=2000 | 正常 | 37 字符 | 34 / 20 | `stop` |
| 思考 low，max=2000 | 正常 | 46 字符 | 34 / 26 | `stop` |

换成**真实提示词**（系统提示 + 政策片段 + 资料）后，问题被放大：

```
flash，思考默认，max_tokens=3000
第 1 次：14s，输出 3000 token（用满），finish_reason=length，content 为空
第 2 次：14s，输出 2999 token（用满），finish_reason=length，content 为空
```

**结论**：官方文档提到的"JSON 模式偶发返回空内容"，在本项目里可以由一个明确原因触发——思考 token 先消耗预算，正文还没开始写就被截断。这不是模型拒答，也不是 JSON 格式错误。若按"模型没话说"处理，用户会看到一个没有结论的结果页。

---

## 四 实验二：端到端核验链路

用同一份文档与问题，比较三种配置（全部走 `_parse_payload` + `verify_report`）：

| 配置 | 耗时 | 输出 token | 条件数 | 引用核验 | 观察 |
|---|---|---|---|---|---|
| flash，关闭思考，max=3000 | 7.3s | 1974 | 17 | **12/12 通过** | 最快最省；把 7 条材料项当成"已满足的条件" |
| flash，思考 low，max=16000 | 43.2s | 11007 | 11 | **14/14 通过** | 慢 6 倍、贵 5 倍；把用户已提供的学历、社保判成 NEEDS_INPUT |
| v4-pro，关闭思考，max=3000 | 9.1s | 1084 | 11 | **6/6 通过** | 条件划分最干净；有一条 UNKNOWN 却附了已核验引用 |

补充说明：

- 三次调用的引用**全部通过逐字核验**，没有出现编造引用。
- 但样例文档只有两页、检索片段很小，逐字引用本来就容易。**这不代表模型不会编造引用**，核验的拒绝路径目前仍只由离线 demo 的埋设缺陷覆盖。
- v4-pro 的那条 UNKNOWN 同时附了一条真实引用：结论状态与证据强度不一致，属于需要单独分类的问题，已转给 E。

---

## 五 结论：P06 的五条实现要求

1. **默认关闭思考模式**（`extra_body={"thinking": {"type": "disabled"}}`）。实测最快最省，判定质量不更差。
2. **`max_tokens` 不得低于 2000**，默认 3000 起步。
3. **空内容要分类**：`finish_reason == "length"` 且 `content` 为空 = 推理吃光预算导致的截断，属可重试；`content` 非空但 JSON 不合法才是格式错误。两类错误标识必须分开。
4. **只读 `message.content`**：推理文本在独立的 `reasoning_content` 字段，不得混入正文或引用。
5. **提示词要约束"条件"与"材料"的边界**，避免把材料清单逐条当成已满足的条件。

---

## 六 成本参考

| 配置 | 输入 token | 输出 token | 谷时单次成本 |
|---|---|---|---|
| flash，关闭思考 | 923 | 1974 | 约 **$0.0013** |
| flash，思考 low | 948 | 11007 | 约 $0.0067 |
| v4-pro，关闭思考 | 920 | 1084 | 约 $0.0028 |

峰时（周一至周五 01:00–04:00、06:00–10:00 UTC）翻倍。计价见 `docs/credentials.md` 第七节。

---

## 七 本次未覆盖的内容

1. **模型质量评估**：需要不少于 20 例、分项给出样本数，由 E 在 P09 执行；验收集由 B 在 P03 产出。
2. **核验拒绝路径**：真实模型本次没有给出编造引用，因此"引用无法定位即整条降级"目前仍只被离线 demo 验证过。
3. **长文档与多页 PDF**：只测了 2 页纯文本；`pypdf` 抽取、分页、大文件上限均未验证。
4. **对抗输入**：文档内提示注入（T08）、超长上下文、并发与限流都未测试。
5. **v4-pro 的思考模式**：只测了关闭思考。
6. **真实服务端**：仓库目前还没有 HTTP 接口，本次是脚本级验证，不是服务级验证。

---

## 八 复现方式

前置：本机已配置 `DEEPSEEK_API_KEY`（见 `docs/credentials.md`），并已执行 `pip install -e ".[dev,server]"`。

```powershell
$env:DEEPSEEK_API_KEY = "<你的密钥>"   # 不要写进任何文件
python -m pytest -q                     # 132 passed
```

关键参数（P06 实现时照此设置）：

```python
client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    response_format={"type": "json_object"},
    max_tokens=3000,
    extra_body={"thinking": {"type": "disabled"}},
)
```

判断结果是否仍然成立时，先看 `finish_reason` 与 `content` 长度，再看 `verify_report` 的统计——顺序反了容易把截断误判成模型编造。
