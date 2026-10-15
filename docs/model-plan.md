# MathGuide 模型接入方案

本方案采用已配置的 Ollama 本地服务，使用 Qwen2.5-3B 量化模型。

## 指定模型与运行平台

- 模型：Qwen2.5-3B-Instruct。
- 指定文件名：`qwen2.5-3b-instruct-q4_k_m.gguf`。
- 格式：GGUF，量化方式 Q4_K_M。
- 平台：Ollama 0.12.3，本机地址 `http://127.0.0.1:11434`。
- 项目接入：Python 模型适配层通过 Ollama SDK 调用。

文件来源仓库、实际大小及哈希需在部署时核验。该文件名不证明来源是 Unsloth 官方仓库，不预先声称已取得或验证模型。

## 调用与职责

文字或OCR校对题干由Python发送给模型，附知识点编号目录。模型返回题型和知识点编号，程序校验JSON及编号并查询SQLite公式库。题干、公式卡片和教学规则进入下一次模型调用，模型组织启发式对话，程序控制轮次和归档。专项练习仍由Python模板生成和精确判分，不依赖模型。

`llm.py`继续使用 Ollama SDK，`config.py`中的模型标识为 `mathguide-qwen25-3b:latest`，由原模型 `qwen25-3b:latest` 派生，复用现有权重。已核验服务返回 GGUF、Qwen2、约3.4B参数、Q4_K_M。默认只允许本机连接，不开放远程服务。

## 实施与验证

1. 核验文件来源、许可、大小和哈希，并检查设备资源。
2. 在Ollama中确认模型标签、聊天模板与结束标记。
3. 配置本地模型标识，运行 MathGuide 健康检查。
4. 用题库检查知识点匹配、JSON格式、算术表达、引导行为和延迟。
5. 保留知识库、OCR、学习档案及练习模块，不把量化模型当作数学正确性的保证。

GGUF用于本地推理。如后续微调，应另取得可训练的基础权重，在Unsloth中训练后导出和量化，不直接把本GGUF当作训练权重。

## 方案与代码边界

当前`llm.py`和`config.py`已按 Ollama 服务与 `mathguide-qwen25-3b:latest` 配置。

## 2026-10-13 聊天模板修复

原模型模板仅为 `{{ .Prompt }}`，实测出现指令遵循不稳定和重复输出。项目专用配置见 `models/Modelfile.qwen25-mathguide`：显式保留每条消息的角色和 Qwen 消息边界，设置停止标记、8192 上下文、512 输出上限及重复惩罚。分类调用使用温度0和256输出上限；辅导使用温度0.2和512输出上限。

重建命令：`ollama create mathguide-qwen25-3b -f models/Modelfile.qwen25-mathguide`。保留原模型，可通过修改 `config.py` 回退。

验证：简短指令准确回答后正常停止；真实长方形面积题成功返回知识点编号；两轮辅导没有直接泄露最终答案，并返回 CONTINUE 标记；64项自动化测试通过。这些样例不代表所有题目都能正确遵循指令，后续需扩大题库评估。

官方依据：

- https://unsloth.ai/docs/new/studio
- https://unsloth.ai/docs/basics/inference-and-deployment/saving-to-gguf
