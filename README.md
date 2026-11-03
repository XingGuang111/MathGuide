# MathGuide

**面向小学生的本地 AI 数学辅导与学习陪伴系统。**

MathGuide 通过“读懂题意 → 寻找方法 → 列式计算”的分步对话，引导学生自主解题，并将作业、反思、错题与针对性练习连接起来。项目使用 Ollama 在本机运行大模型，提供浏览器界面和命令行入口，无需云端 API Key。

## 功能概览

- **启发式辅导**：结合学生回答调整提示，支持关键词解释、小例子和分步计算；区分独立解出与讲解后完成。
- **拍照录题**：使用 RapidOCR 识别印刷体题目，支持 JPG、JPEG、PNG、BMP；识别后可以校对题干。
- **每日作业**：文字或多图录入清单，逐题作答、AI 分析、订正和反思；配图题可调用本地视觉模型。
- **学习档案**：保存对话、作业记录、学习笔记和错题，统计薄弱知识点并生成专项练习。
- **知识与计算核验**：内置小学数学公式库，对部分常见题型和纯算式进行程序核验。
- **学习宠物“星芽”**：提供鼓励对话、成长奖励、商店、动作与帽子装扮；学习获得活力后可开启限时玩耍。
- **本地存储与局域网访问**：学习记录保存在 SQLite，电脑提供服务，同一局域网的手机或平板可通过浏览器访问。

模型、依赖和素材准备完成后，核心辅导可在本地运行。首次安装及模型下载需要联网；实际响应速度取决于硬件和所选模型。

## 快速启动

### 1. 准备运行环境

| 组件 | 要求 / 建议 |
| --- | --- |
| Python | 3.10 或以上，建议使用 64 位 Python 3.11 / 3.12 |
| Ollama | 安装当前版本：[官方下载](https://ollama.com/download) |
| 浏览器 | 推荐新版 Chrome / Edge，便于播放宠物透明动画 |
| 内存与磁盘 | 建议至少 8 GB 内存，使用视觉模型建议 16 GB 或以上；预留数 GB 以上空间用于模型，具体以下载大小为准 |
| Git | 可选；也可以直接下载 ZIP |

Windows 安装 Python 时请勾选 **Add python.exe to PATH**。安装完成后重新打开终端，确认以下命令可用：

```sh
python --version
ollama --version
```

macOS / Linux 通常使用 `python3 --version`。不要求安装 Node.js、npm 或独立数据库服务，前端由 Python 服务直接提供。

### 2. 下载项目

**方式一：使用 Git**

```sh
git clone https://github.com/XingGuang111/MathGuide.git
cd MathGuide
```

**方式二：下载 ZIP**

打开 [GitHub 仓库](https://github.com/XingGuang111/MathGuide)，选择 **Code → Download ZIP**，解压后在项目文件夹中打开终端。下载后的文件夹可能叫 `MathGuide-main`，请以实际名称为准。

后续命令都在包含 `README.md`、`requirements.txt` 和 `web_app.py` 的项目根目录执行，不要在压缩包内直接运行。

### 3. 创建虚拟环境并安装依赖

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

这里直接使用虚拟环境内的 Python，无需激活脚本，也不会遇到 PowerShell 阻止执行 `Activate.ps1` 的问题。如果找不到 `python`，可尝试用 `py -3 -m venv .venv` 创建环境。

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

如果 Linux 提示缺少 `venv`，请先通过系统包管理器安装对应 Python 版本的 venv 组件，例如 Ubuntu / Debian 的 `python3-venv`。

如果下载依赖很慢，可在安装命令后添加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` 使用清华 PyPI 镜像，例如 Windows：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

安装完成后，可用虚拟环境的 Python 执行 `python -m pip check`；预期显示 `No broken requirements found.`。

### 4. 启动 Ollama 并准备文本模型

打开 Ollama 应用，或在单独的终端运行以下命令，并保持该终端开启：

```sh
ollama serve
```

如果 Ollama 已在后台运行，就不需要再次执行；出现默认端口 `11434` 已占用时，先通过 `ollama list` 确认服务是否已经可用。

在**项目根目录的终端**依次执行：

```sh
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama create mathguide-qwen25-3b -f models/Modelfile.qwen25-mathguide
ollama list
```

下载耗时取决于网络。`ollama list` 中应出现 **`mathguide-qwen25-3b:latest`**，与 `config.py` 的 `MODEL_NAME` 一致。该名称是本项目在本地创建的模型，不能用 `ollama pull mathguide-qwen25-3b` 代替创建步骤。

**可选：配图作业的视觉模型**

如果需要分析几何图、阴影、网格或图形选项，再下载：

```sh
ollama pull qwen2.5vl:3b
```

纯文字辅导和普通 OCR 文字识别不需要这个视觉模型。

### 5. 启动网页服务

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe web_app.py
```

**macOS / Linux**

```bash
.venv/bin/python web_app.py
```

保持终端开启，在浏览器访问 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**。看到 Uvicorn 启动日志表示网页服务已运行；首次启动会自动创建数据库并导入公式，无需手动建表。

首次加载模型可能较慢。可以打开 [健康检查](http://127.0.0.1:8000/api/health)，确认返回的 `ok` 为 `true`，且 `model` 为 `mathguide-qwen25-3b:latest`。健康检查确认文本模型服务和模型名称可用，不验证视觉模型或实际答题质量。

### 6. 试一道题

在“AI 辅导”中输入：

> 一块长方形菜地长 12 米，宽 8 米，它的面积是多少平方米？

根据老师的问题逐步回答已知条件、计算方法和结果。也可以进入“今日作业”录入清单，完成后在“学习档案”查看记录。

按 `Ctrl+C` 停止网页服务。**以后启动**只需保证 Ollama 正在运行，在项目根目录重新执行第 5 步的命令，无需重复安装依赖或下载模型。

## 使用方式

### 网页入口

| 页面 | 本机地址 |
| --- | --- |
| AI 辅导 | [首页](http://127.0.0.1:8000/) |
| 今日作业 | [作业清单](http://127.0.0.1:8000/?view=homework) |
| 学习档案 | [记录、笔记与错题](http://127.0.0.1:8000/?view=learning) |
| 宠物商店 | [星芽商店](http://127.0.0.1:8000/?view=shop) |
| API 文档 | [Swagger UI](http://127.0.0.1:8000/docs) |

网页须通过运行中的服务访问，不要直接双击 `web/index.html`。

### 手机 / 平板访问

1. 电脑启动网页服务，手机或平板连接到同一局域网。
2. 在 Windows 终端执行 `ipconfig`，查找当前网络的 IPv4 地址，例如 `192.168.1.100`。
3. 在移动设备浏览器中打开 `http://192.168.1.100:8000`，替换为实际电脑地址。
4. 如防火墙询问访问权限，允许专用网络访问；电脑需保持开机，服务终端需保持运行。

`python web_app.py` 默认监听 `0.0.0.0:8000`。当前服务没有完整的账号认证与数据隔离，适合个人或可信家庭局域网使用，不应直接开放到公网。若只需本机访问，可使用虚拟环境中的 Python 执行：

```sh
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

上述 `python` 在 Windows 对应 `.\.venv\Scripts\python.exe`，在 macOS / Linux 对应 `.venv/bin/python`。

### 命令行模式

将网页启动命令中的 `web_app.py` 替换为 `main.py` 即可，例如 Windows：

```powershell
.\.venv\Scripts\python.exe main.py
```

| 输入 | 功能 |
| --- | --- |
| 直接输入题目 | 开始启发式辅导 |
| `/photo 图片路径` | OCR 识别图片，确认或修正题目后开始辅导 |
| `/history` | 查看历史记录 |
| `/history 2026-11-02` | 按日期筛选记录 |
| `/history 几何应用题` | 按题型筛选记录 |
| `/stats` | 查看薄弱知识点统计 |
| `/new` | 结束当前题目，开始新题 |
| `/help` | 查看帮助 |
| `/quit` | 退出 |

### 星芽陪伴

学习档案保存星星、成长、已学动作和装扮。经服务端核验的学习活动可获得活力，20 活力可开启 2 分钟玩耍，每日默认最多 10 分钟；活力按北京时间跨天重置，星星与已购道具保留。宠物对话提供鼓励，不参与判分。

“娱乐模式”可通过内置体验密码 `xingya` 进入独立宠物档案，体验动作和装扮；退出后恢复原学习宠物。该密码仅用于演示入口，不是账号认证机制。

## 配置与数据

主要配置位于 [`config.py`](config.py)，修改后重启服务：

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `MODEL_NAME` | `mathguide-qwen25-3b:latest` | 文本辅导与宠物对话模型 |
| `VISION_MODEL_NAME` | `qwen2.5vl:3b` | 配图作业视觉模型 |
| `MAX_GUIDE_ROUNDS` | `12` | 单题最大引导轮数 |
| `VISION_TIMEOUT_SECONDS` | `120` | 视觉请求超时秒数 |
| `PET_CHAT_TIMEOUT_SECONDS` | `25` | 宠物对话超时秒数 |
| `PET_DAILY_PLAY_MINUTES` | `10` | 每个学习档案每日玩耍额度 |
| `ENABLE_MODEL_DIAGNOSIS` | `True` | 启用模型诊断学生回答 |
| `ENABLE_MODEL_DIALOGUE` | `True` | 启用模型组织教学回复 |
| `ENABLE_MODEL_OPENING` | `True` | 启用模型生成首次提问 |

若更换模型，请先用 Ollama 下载或创建，再将 `MODEL_NAME` 改为 `ollama list` 中的完整名称。不同模型对 JSON 协议和教学提示词的遵循能力不同，需要重新验证效果。

教学规则与示例可直接维护，程序会在后续回复时读取更新：

- [`docs/system prompt.txt`](docs/system%20prompt.txt)：通用要求与各教学阶段规则。
- [`docs/primary_math_tutor.jsonl`](docs/primary_math_tutor.jsonl)：按阶段、知识点组织的短示例。
- [`docs/Dialogue Example.md`](docs/Dialogue%20Example.md)：完整对话及标记为 `tutor-example` 的可用片段。

这些文件调整运行时提示与示例，不会训练或修改模型权重。

运行数据默认保存到：

- `data/mathguide.db`：学习记录、作业、照片、反思和宠物数据。
- `data/mathguide.sessions.json`：Web 辅导会话快照。
- 浏览器本地存储：当前会话、宠物档案编号等；清除浏览器数据可能丢失本机与档案的关联。

备份时先停止服务，再复制数据库及会话快照；恢复时放回原位置。公式种子文件 [`data/formulas.json`](data/formulas.json) 属于项目必需文件。个人数据库、会话快照和虚拟环境不应提交到 GitHub，运行数据可能含学生照片与对话。

## 项目结构与技术栈

```text
MathGuide/
├── main.py                  # 命令行入口
├── web_app.py               # FastAPI 接口与网页入口
├── agent.py                 # 辅导状态机与会话流程
├── llm.py / vision.py       # Ollama 文本与视觉模型调用
├── teaching.py              # 教学动作与学生状态
├── scaffolding.py           # 分步引导
├── prompts.py               # 提示词与模型协议
├── calculation.py           # 常见题型计算核验
├── ocr.py                   # RapidOCR 图片识别
├── homework*.py             # 作业录入、分析与看图辅导
├── practice.py              # 专项练习
├── knowledge.py / db.py     # 知识查询与 SQLite 存储
├── pet*.py                  # 宠物、对话、商店、表情与活力
├── config.py                # 全局配置
├── requirements.txt         # 运行依赖
├── requirements-dev.txt     # 测试依赖
├── data/formulas.json       # 公式种子数据
├── models/                  # Ollama Modelfile
├── web/                     # HTML、原生 JavaScript、CSS 与本地素材
├── tests/                   # pytest 测试
├── tools/                   # 演示、验证和素材维护脚本
└── docs/                    # 设计说明、提示词和测试记录
```

后端使用 **FastAPI + Uvicorn**，数据使用 **SQLite**，本地推理使用 **Ollama + Qwen2.5**，OCR 使用 **RapidOCR + ONNX Runtime**。前端不需要额外构建。

## 开发与测试

在已安装运行依赖的虚拟环境中执行：

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**macOS / Linux**

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

自动化测试主要使用临时数据库和模型替身；测试通过不能替代真实模型效果验证。`tools/` 中的浏览器、模型和演示脚本有各自的环境要求，不是快速启动的必需步骤。历史测试结果以对应日期的文档为准，不代表当前版本已重新执行全部验证。

提交 Issue 时建议附上操作系统、Python / Ollama 版本、复现步骤及去除个人信息后的报错。提交代码前请运行相关测试，并同步更新使用说明。

## 常见问题

| 问题 | 排查方式 |
| --- | --- |
| 找不到 Python / Ollama 命令 | 确认已安装并加入 PATH，重新打开终端；Windows 可尝试 `py -3`。 |
| `ModuleNotFoundError` | 使用第 3 步创建的虚拟环境安装依赖，并用同一个环境的 Python 启动。 |
| Linux 提示缺少 `libGL.so.1` / `libgthread-2.0.so.0` | OpenCV 需要系统库；Ubuntu / Debian 可执行 `sudo apt install libgl1 libglib2.0-0`，其他发行版安装对应组件。 |
| 无法连接 Ollama | 确认 Ollama 应用或 `ollama serve` 正在运行，执行 `ollama list` 检查连接。 |
| 找不到 `mathguide-qwen25-3b:latest` | 重新执行第 4 步的 `ollama create`，不要直接拉取这个本地自定义名称。 |
| `ollama create` 找不到 Modelfile | 将终端切换到项目根目录，确认 `models/Modelfile.qwen25-mathguide` 存在。 |
| 网页能打开，但不能辅导 | 查看 `/api/health` 的 `ok` 与 `message`，并检查服务终端日志；首页可打开不代表模型已经就绪。 |
| 配图作业无法分析 | 执行 `ollama pull qwen2.5vl:3b`，核对 `VISION_MODEL_NAME`，并检查内存和图片清晰度。 |
| OCR 内容不准 | 尽量使用清晰、正向、光线均匀的印刷体图片；发布或辅导前校对识别结果，手写与复杂公式可能识别不准。 |
| `8000` 端口被占用 | 关闭重复启动的服务，或用虚拟环境 Python 执行 `python -m uvicorn web_app:app --host 127.0.0.1 --port 8001`，再访问端口 `8001`。 |
| 手机无法访问 | 检查是否同一局域网、电脑防火墙是否允许端口 8000，以及服务是否仍在运行；手机上的 `127.0.0.1` 指向手机自己。 |
| 模型回复慢或超时 | 首次加载需要等待；关闭占用内存的程序，先验证文本辅导，再尝试视觉模型。 |
| 提示“回复未通过教学检查，请重试” | 当前模型回复未满足教学约束，重新提交这一轮回答；若持续出现，查看服务日志并附题目与复现步骤反馈。不要将健康检查通过理解为每轮生成均可靠。 |
| 宠物动画不能播放 | 使用新版 Chrome / Edge，确认 `web/assets/pet/` 素材完整；不支持透明 WebM 时可能显示静态备用图。 |

模型生成、图像理解与 OCR 都可能出错，程序核验也只覆盖部分题型。作业的“AI 分析通过”不等同于学生已经独立掌握，重要结论应结合原题复核。

## 更多文档

- [安装与启动验证记录（含未通过项）](docs/installation-verification.md)
- [GitHub 发布完整性检查](docs/github-release.md)
- [每日作业流程](docs/homework-ui.md)
- [计算核验设计](docs/calculation-verification.md)
- [专项练习设计](docs/practice-design.md)
- [存储设计](docs/storage-design.md)
- [提示词设计](docs/prompt-design.md)
- [启发式辅导验证记录（2026-11-01）](docs/socratic-validation-2026-11-01.md)
- [产品测试与演示记录（2026-10-29）](docs/test-record-2026-10-29.md)
- [真实测试与学习档案记录（2026-10-29）](docs/learning-real-test-2026-10-29.md)

## 许可与致谢

### 数学辅导与提示词设计参考

MathGuide 的教学流程、提示词规则和回复策略参考了以下公开 GitHub 项目。感谢这些项目的作者分享数学辅导和学习引导的设计：

| 参考项目 | 本项目借鉴的内容 |
| --- | --- |
| [gpoesia/socratic-tutor](https://github.com/gpoesia/socratic-tutor) | 用明确状态、动作和完成条件组织数学辅导；由确定性逻辑核验可验证的答案。 |
| [hwl668/Scientific-learning-skills-](https://github.com/hwl668/Scientific-learning-skills-) | problem-solving Skill 中的题型分析、关键条件、分步求解与变式练习；针对学生卡点选择教学动作。 |
| [Bhala-Srinivash/agent-tutor-skill](https://github.com/Bhala-Srinivash/agent-tutor-skill) | Explain → Example → Check → Evaluate → Practice 的学习循环，以学生实际作答作为掌握证据。 |
| [rocklogic11/k12-math-tutor](https://github.com/rocklogic11/k12-math-tutor) | K12 数学辅导中的显式分步与计算复核；结合本项目需求改为多轮启发式引导。 |

上述来源依据项目已有的[调研与落地记录](docs/math-tutor-github-research-2026-10-29.md)整理，主要影响 [`docs/system prompt.txt`](docs/system%20prompt.txt)、[`prompts.py`](prompts.py) 和 [`teaching.py`](teaching.py) 中的教学约束与回复组织。该记录记载的是设计原则借鉴，并未记载复制上游代码或提示词全文；具体引用范围和来源说明见[第三方参考与致谢](docs/acknowledgements.md)。

### 代码与素材许可

MathGuide 原创代码采用 [MIT License](LICENSE)。第三方代码、模型与素材仍遵循各自许可，不包含在本项目的 MIT 授权范围内。

宠物形象和动画来自 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)，部分动作清单参考 [youxin484/dsh-dafeiyu-enhanced](https://github.com/youxin484/dsh-dafeiyu-enhanced)。**第三方素材有独立的非商用及署名要求，不能将代码的 MIT 许可理解为全部素材可商用。**

素材来源、固定版本、哈希及具体条款见：

- [素材使用说明](web/assets/pet/ASSET-NOTICE.md)
- [来源与导入记录](web/assets/pet/SOURCES.md)
- [上游原始说明](web/assets/pet/UPSTREAM-README.md)
- [上游代码许可证](web/assets/pet/LICENSE.txt)

Ollama、Qwen 模型及其他依赖遵循各自许可证与使用条款。
