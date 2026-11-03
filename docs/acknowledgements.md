# 第三方参考与致谢

感谢公开分享教学方法、提示词设计和软件实现的作者。MathGuide 的数学 AI 回复策略在项目迭代中参考了以下资料，并结合小学数学、多轮引导和本地模型运行的需求进行组织与调整。

## 教学流程、提示词与回复策略

| 项目与作者 | 参考内容 | 在 MathGuide 中的对应设计 |
| --- | --- | --- |
| [gpoesia/socratic-tutor](https://github.com/gpoesia/socratic-tutor) | 数学教学领域的状态、动作与完成条件 | `agent.py` 的阶段推进、`calculation.py` 的程序核验，以及“完成条件由程序检查”的提示规则。 |
| [hwl668/Scientific-learning-skills-](https://github.com/hwl668/Scientific-learning-skills-) | problem-solving Skill 的题型、条件、模型、分步求解与变式训练 | `teaching.py` 的卡点诊断与教学动作、`scaffolding.py` 的小步骤，以及提示规则中的针对性帮助。 |
| [Bhala-Srinivash/agent-tutor-skill](https://github.com/Bhala-Srinivash/agent-tutor-skill) | Explain、Example、Check、Evaluate、Practice 循环，以作答验证掌握 | 解释概念、举小例子、检查回答、提供练习；区分“看过讲解”和“独立解出”。 |
| [rocklogic11/k12-math-tutor](https://github.com/rocklogic11/k12-math-tutor) | 显式分步与计算复核 | 小学数学分步教学和结果检查；未采用其面向完整解题的长篇回答模板。 |

来源依据：[2026-10-29 调研与落地记录](math-tutor-github-research-2026-10-29.md)。对应文件表示本项目的实现位置，不表示这些文件整体来自上游。

现有记录说明，本次参考以通用教学流程与设计原则为主，没有复制上游代码或提示词全文。现有记录没有逐段提示词引用、上游提交哈希或逐项许可证核验，因此此处不虚构具体版本、复制范围或许可证。各来源的授权范围以对应项目的许可证及权利人说明为准，致谢本身不替代许可。

如后续引入具体提示词片段、示例数据或代码，应在此补充上游文件链接、固定提交版本、改写范围和适用许可，并按上游要求保留版权与许可文本。

以上项目提供了设计参考，不表示其作者参与开发、为 MathGuide 背书，或本项目具有经过对照实验验证的教学效果。

## 宠物形象与动画

- [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)：宠物形象及动画来源。
- [youxin484/dsh-dafeiyu-enhanced](https://github.com/youxin484/dsh-dafeiyu-enhanced)：部分动作清单参考。

素材实际导入的固定版本、文件哈希和署名说明保存在 [`web/assets/pet/SOURCES.md`](../web/assets/pet/SOURCES.md) 及该目录的素材清单中。角色、动画和衍生截图适用独立素材条款，详见[素材使用说明](../web/assets/pet/ASSET-NOTICE.md)，不能仅依据上游代码的 MIT 许可证判断素材授权。

## 基础技术

感谢 [Ollama](https://github.com/ollama/ollama)、[Qwen2.5](https://github.com/QwenLM/Qwen2.5)、[Qwen2.5-VL](https://github.com/QwenLM/Qwen2.5-VL)、[RapidOCR](https://github.com/RapidAI/RapidOCR)、[FastAPI](https://github.com/fastapi/fastapi) 等项目及依赖维护者。依赖包与模型分别遵循其自身许可证和使用条款。
