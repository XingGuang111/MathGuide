# MathGuide

基于本地轻量大模型的小学数学启发式错题辅导系统。拍照搜题 → 智能分析 → 逐步引导学生自主思考，而不是直接给答案。

## 功能亮点

- **拍照搜题**：本地 RapidOCR 离线识别印刷体题目，支持 jpg/png/bmp
- **启发式辅导**：苏格拉底式提问引导，最多 12 轮，学生独立解出才标记掌握
- **公式知识库**：50+ 条小学数学公式，按知识点匹配，含易错提示和别名兜底
- **薄弱知识点练习**：根据历史记录自动生成针对性练习，闭环巩固
- **计算核验**：常见题型（长方形面积/周长、分数运算等）自动核验答案
- **纯本地运行**：模型走 Ollama，数据存 SQLite，不依赖任何云端 API
- **双入口**：终端 REPL + FastAPI Web 服务（含静态前端页面）

## 架构

```
┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
│  终端 REPL    │     │  Web 前端     │     │   Ollama 模型    │
│  (main.py)    │     │ (web/index)   │     │ Qwen2.5-3B 量化  │
└──────┬───────┘     └──────┬───────┘     └────────┬────────┘
       │                    │                       │
       └─────────┬──────────┘                       │
                 ▼                                  ▼
┌────────────────────────────────────────────────────────────┐
│                  TutorAgent 状态机                         │
│  分析 → 公式卡 → 引导 → 标记理解 → 归档                    │
└──────┬───────────┬───────────────┬───────────────┬────────┘
       │           │               │               │
       ▼           ▼               ▼               ▼
   公式知识库   计算核验        OCR 引擎       SQLite 存储
 (formulas.json) (calculation)  (RapidOCR)    (学习档案)
```

## 目录结构

```
MathGuide/
├── agent.py            # 启发式辅导状态机（核心）
├── main.py             # 终端 REPL 入口
├── web_app.py          # FastAPI Web 服务入口
├── llm.py              # Ollama 模型调用封装
├── ocr.py              # RapidOCR 拍照搜题封装
├── prompts.py          # 系统提示词与模型协议
├── calculation.py      # 常见题型计算核验
├── practice.py         # 薄弱知识点练习生成
├── knowledge.py        # 公式知识库查询
├── db.py               # SQLite 数据访问层
├── config.py           # 全局配置
├── data/
│   └── formulas.json   # 小学数学公式种子数据
├── models/
│   └── Modelfile.qwen25-mathguide  # Ollama 模型配置
├── web/                # 静态前端（HTML + 原生 JS）
├── tests/              # pytest 单元测试
└── docs/               # 设计文档
```

## 快速开始

### 环境要求

- Python 3.10+
- [Ollama](https://ollama.com/) 本地服务
- 至少 4GB 可用内存（运行 Qwen2.5-3B Q4 量化模型）

### 安装

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 拉取并创建模型（首次运行）
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama create mathguide-qwen25-3b -f models/Modelfile.qwen25-mathguide
```

### 终端模式

```bash
python main.py
```

可用命令：
- 直接输入题目 → 开始辅导
- `/photo 图片路径` → 拍照搜题
- `/history` → 查看历史记录
- `/stats` → 薄弱知识点统计
- `/new` → 放弃当前题目
- `/help` → 帮助

### Web 模式

```bash
python web_app.py
# 浏览器打开 http://127.0.0.1:8000
```

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 大模型 | Ollama + Qwen2.5-3B-Instruct (Q4_K_M 量化) |
| OCR | RapidOCR (ONNXRuntime) |
| 后端 | FastAPI + Uvicorn |
| 前端 | 原生 HTML + JavaScript |
| 数据库 | SQLite |
| 终端 | Python REPL |

## License

MIT
