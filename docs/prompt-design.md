# MathGuide 提示词工程维护说明

本文对应当前的三阶段辅导、模型诊断和自然回复流程。文件索引见 [README](../README.md#提示词工程在哪里)。提示词调整模型行为；程序还会独立核验受支持题型、阶段推进和回复约束。

## 1. 可编辑教学资料

| 文件 | 内容与加载方式 |
| --- | --- |
| [system prompt.txt](system%20prompt.txt) | `[global]`、`[understand]`、`[method]`、`[compute]` 分节规则 |
| [primary_math_tutor.jsonl](primary_math_tutor.jsonl) | 每行一个 JSON 示例，必需字段为 `id`、`stage`、`topics`、`messages`；可选 `action`、`intent`、`term`、`template` |
| [Dialogue Example.md](Dialogue%20Example.md) | 完整对话供人阅读；只有 `<!-- tutor-example: {...} -->` 后的 `text` 代码块作为机器可读示例 |

读取入口是 [tutor_profile.py](../tutor_profile.py) 的 `load_profile()`，路径由 [config.py](../config.py) 的 `TUTOR_SYSTEM_PATH`、`TUTOR_EXAMPLES_PATH`、`TUTOR_DIALOGUE_PATH` 指定。按文件修改时间及大小刷新缓存，文件变更在后续读取时生效。

`build_context()` 按阶段、题型与表达意图选取最多两个短示例，拼入阶段提示。`render_response()` 根据动作选择提示模板；`term_examples()` 提供概念解释素材。损坏示例会记录警告并跳过，缺失规则有默认回退，但部署时仍应保留这些资料文件。

这些资料并非每次都全文发送给模型。默认自然回复会根据本轮核验事实重新组装消息，所以只改资料文件不一定改变某条回复的全部约束。

## 2. 模型请求的提示词入口

主要位于 [prompts.py](../prompts.py)：

| 任务 | 入口 |
| --- | --- |
| 判断小学数学、题型和知识点 | `ANALYZE_SYSTEM`、`build_analyze_prompt()` |
| 未匹配本地卡片时生成知识卡或反问 | `GENERATE_FORMULA_SYSTEM`、`build_generate_formula_prompt()` |
| 诊断学生本轮卡点 | `DIAGNOSIS_SYSTEM`、`build_diagnosis_messages()` |
| 组织开场问题 | `build_opening_messages()` |
| 读懂题目、找到方法、列式计算 | `build_stage1_prompt()`、`build_stage2_prompt()`、`build_stage3_prompt()` |
| 生成学生最终看到的自然回复 | `build_reply_messages()` |
| 组织完整讲解 | `EXPLAIN_SYSTEM`、`build_explain_messages()` |
| 概念解释、方法提示、阶段衔接、完成提醒 | `build_understanding_hint()`、`build_method_hint()`、`build_stage_transition()`、`build_completion()` 等 |

[agent.py](../agent.py) 的 `_system_prompt()` 追加上一阶段回答、当前教学动作、已确认事实和近期提问；`_natural_reply()` 将学生对话、程序核验结果、诊断与提示交给 `build_reply_messages()`，并在生成不合格时组装重写提示。

[llm.py](../llm.py) 发起模型调用并检查格式；[model_gateway.py](../model_gateway.py) 适配 Ollama 和兼容接口，并在在线 JSON 请求中补充格式要求。[model_settings.py](../model_settings.py) 选择模型，不定义教学规则。

## 3. 一轮辅导怎样运行

1. `student_input.py` 分离题目和开场尝试，并对受支持的算式表达做有限规范化。
2. `agent.py` 结合历史决定当前阶段；`understanding.py` 累计读题事实，`calculation.py` / `simple_work.py` 核验受支持的算式、结果和单位。
3. `llm.diagnose()` 获取模型诊断建议，`teaching.py` 以程序证据约束诊断、选择教学动作；`scaffolding.py` 按困难程度拆小问题。
4. `prompts.py` 组织提示，默认由 `llm.compose_reply()` 生成自然回复。
5. `agent.py` 与 `reply_guard.py` 检查阶段、数字、重复提问、过早宣布完成等问题；不合格时重写，仍不合格返回可重试错误。
6. 成功回复后更新对话与进度；`session_summary.py` 从题目条件和确认过的证据生成左侧小笔记。

小笔记不是由模型自由总结。遇到条件、目标或思路显示错误，先检查输入拆分、题型识别和证据累计，不能只修改模型提示词。

## 4. 输出协议与完成条件

- **诊断请求**：JSON 包含 `error_type`、`next_action`、`confidence`、`reason`。模型置信度只用于筛选建议，不直接用于判分或宣布掌握。
- **默认自然回复**：JSON 只有 `reply` 字符串。`agent.py` 解析并核验正文后再展示，不把内部 JSON 放进聊天框。
- **阶段对话调用**：正文末尾使用唯一的 `[CONTINUE]` 或 `[UNDERSTOOD]` 标记，由 `llm.chat_stream()` 校验。标记供程序使用，返回学生前剥离；不是所有模型调用都用这个协议。
- **数学核验**：受支持题型使用确定性核验，并非只在专项练习中核验。未覆盖题型仍有模型判断的局限，JSON 合法不等于数学结论正确。
- **完成状态**：列式正确、得数正确、单位正确分开累计。只说“懂了”不表示整题完成；请求完整讲解或达到兜底条件后标记为看过讲解，不冒充独立解出。

“本轮回复未通过教学核验”表示模型生成的教学回复未通过检查，不表示学生本轮答案一定错误。排查时查看 `agent.py` 的拒绝日志、当前阶段和核验事实。

## 5. 其他功能的提示词

| 位置 | 用途 |
| --- | --- |
| [homework_review.py](../homework_review.py) 的 `SYSTEM` | 作业提交后的判定、解释与反思 |
| [homework_visual.py](../homework_visual.py) 的 `vision.json_reply()` 调用 | 看图辅导的启发式提问 |
| [visual_reasoning.py](../visual_reasoning.py) 的 `SOLVE_SYSTEM`、`AUDIT_SYSTEM` | 独立解图及候选解析复核 |
| [pet_chat.py](../pet_chat.py) 的 `SYSTEM` | 星芽角色、情绪陪伴和话题边界 |
| [models/Modelfile.qwen25-mathguide](../models/Modelfile.qwen25-mathguide) | 本地消息模板、停止标记、温度和上下文参数；不训练权重 |

修改 Python 中的提示词后重启网页服务。修改 Modelfile 后重新执行 `ollama create mathguide-qwen25-3b -f models/Modelfile.qwen25-mathguide`，仅影响使用该本地模型的请求；在线模型不使用这个 Modelfile。

## 6. 修改后验证

在项目根目录、已安装依赖的 Python 环境中运行：

```sh
python -m pytest tests/test_prompts.py tests/test_tutor_profile.py tests/test_teaching.py tests/test_socratic_flow.py tests/test_rectangle_conversation.py tests/test_session_summary.py -q
```

需要实际模型验证时运行：

```sh
python tools/check_rectangle_conversation.py
python tools/check_tutor_demo.py --output-dir output/tutor-check
```

前者回放长方形面积错法、计算订正和分轮补单位；后者覆盖多种教学场景。两者调用当前配置的真实文字模型，在线调用可能计费，使用隔离数据库并保存输出。示例通过不代表所有题型都可靠，调整模型或教学规则后应重新验证相关场景。
