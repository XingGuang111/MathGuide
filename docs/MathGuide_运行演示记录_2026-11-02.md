# MathGuide 功能运行与演示记录

> 本文所列 `output/` 中的日志、截图和录屏是本地历史验证产物，不包含在 GitHub 源码下载中。当前安装验证结果请参阅 [安装与启动验证记录](installation-verification.md)。

2026 年 11 月 2 日，使用当前项目启动网页，逐项演示题目辅导、OCR、每日作业、带图题、学习档案、专项练习和星芽陪伴，并整理产品经理视角的 PPT 制作脚本。示例题与学生作答为演示输入，教师回复、OCR 和分析结果来自实际运行的产品。

## 打开产品与制作脚本

- [本机 MathGuide 演示](http://127.0.0.1:8000)
- [每日作业示例](http://127.0.0.1:8000/?view=homework&assignment=pm-product-demo)
- [带图题示例](http://127.0.0.1:8000/?view=homework&assignment=pm-visual-demo)
- [学习档案](http://127.0.0.1:8000/?view=learning)
- [星芽商店](http://127.0.0.1:8000/?view=shop)
- [18 页产品经理视角 PPT 制作脚本](<MathGuide_产品经理视角_PPT制作脚本.md>)

脚本包含每页上屏文案、画面安排、口播与功能演示步骤，还附有给 AI 制作工具的整体指令及功能覆盖表。

## 运行环境

| 项目 | 本次状态 |
|---|---|
| 网页 | FastAPI／Uvicorn，`http://127.0.0.1:8000` |
| 文字模型 | `mathguide-qwen25-3b:latest`，健康检查通过 |
| 视觉模型 | 补装 `qwen2.5vl:3b` 后，视觉能力检查通过 |
| OCR | 实际 RapidOCR，本地执行 |
| 学习数据 | `output/product-demo-2026-11-02/runtime/product-demo.db` |
| 辅导快照 | 同目录 `product-demo.sessions.json` |
| 数据性质 | 独立演示档案；未使用模型或 OCR 测试替身 |

本次新增演示启动与采集工具、文档和素材，没有修改产品业务代码或已有路演 PPT。

## 功能与实际结果

| 功能 | 演示操作与结果 |
|---|---|
| 文字题辅导 | 输入长 8 厘米、宽 5 厘米的面积题，按读题、方法、计算推进，提交 `8×5=40平方厘米` 后完成归档 |
| 知识卡片和解题小笔记 | 展示长方形面积公式、易错提醒、已知条件、目标和已确认的方法 |
| 完整讲解 | 对 200 元打八折的题主动请求完整讲解，显示 160 元的解题说明，归档为讲解后复习 |
| 照片 OCR | 生成印刷体示例作业照片，实际识别成 3 道题；保留各题配图，第 3 题提示重点校对 |
| 家长作业录入 | 展示照片导入、待校对题干、题目调序和原图入口；照片清单保留为草稿 |
| 学生每日作业 | 保存并打开 3 道文字题的清单；作答和状态能从服务端恢复 |
| 作业分析 | `36÷6` 答 6 得到分析通过；`8+5` 答 12 得到需订正，纯算式由精确计算核验 |
| 反思和收录 | 保存两道题的反思，两条计入学习笔记，其中错误题加入错题集；页面可筛选并展开 |
| 带图转录 | 视觉模型实际读取轴对称样例，返回转录建议与 `needs_review=true`；图形选项仍需对照原图 |
| 带图核验和辅导 | 轴对称半图补全样例由图形规则核实不可能项为 A，保留逐项依据；看图老师提示观察翻折后的方向 |
| 学习档案 | 显示 2 次辅导：1 道独立解出、1 道讲解后复习；可查看原始师生对话与知识卡 |
| 薄弱点与专项练习 | 折扣问题列为待继续巩固；面积练习三题分别为 `5×7`、`12×5`、`4×6`，连续独立答对后显示初步巩固 |
| 学习奖励 | 一道辅导与三道独立练习共积累 50 星星、50 成长值；活力达到上限 40 |
| 限时玩耍和商店 | 使用 20 活力开启 2 分钟，花 40 星星购买彩虹小球并互动；学习宠物剩余 10 星星，成长值保持 50 |
| 陪伴聊天 | 输入“这题好难，给我加油！”，消息记录确认回复来源为 `local_model` |
| 动作 喂食和帽子 | 独立娱乐档案中表演鲸鱼泡泡、喂冰淇淋、戴星星魔法帽；随后退出，恢复原学习档案 |
| 终端入口 | 实际启动终端程序，执行 `/help`、`/stats`、`/history`、`/quit`，读取同一演示档案 |

视觉样例判定的 `verification` 为 `verified_geometry`，不能将这次图形规则的正确结果说成视觉模型泛化准确率。视觉转录使用了真实模型，但返回的图形选项文字需要校对。

## 主要功能画面

### 题目辅导与解题小笔记

完成面积题的实际对话、知识卡片和解题小笔记（本地文件：`output/product-demo-2026-11-02/screenshots/03-tutor-complete.png`）

### 专项练习与初步巩固

连续独立完成三道同知识点练习（本地文件：`output/product-demo-2026-11-02/screenshots/05-practice-consolidated.png`）

### OCR 作业导入与校对

一张示例照片识别为三道待校对题目（本地文件：`output/product-demo-2026-11-02/screenshots/09-ocr-import.png`）

### 每日作业分析与反思

作业清单、错误答案分析与反思收录（本地文件：`output/product-demo-2026-11-02/screenshots/08-homework-review.png`）

### 学习档案和复习安排

独立解出与讲解后复习的不同记录、复习建议和作业汇总（本地文件：`output/product-demo-2026-11-02/screenshots/14-learning-updated.png`）

### 带图题与看图老师

保留题图、逐项核验依据和看图老师的观察提示（本地文件：`output/product-demo-2026-11-02/screenshots/16-visual-tutor.png`）

### 学习奖励兑换玩耍

花费学习星星购买玩具并在限时窗口内互动（本地文件：`output/product-demo-2026-11-02/screenshots/11-pet-play.png`）

### 帽子装扮

下图为独立娱乐档案，画面中的开放道具与余额不代表学习所得。演示后已退出娱乐模式。

娱乐模式下的帽子装扮（本地文件：`output/product-demo-2026-11-02/screenshots/13-pet-hats.png`）

## 全部截图索引

截图目录为 `output/product-demo-2026-11-02/screenshots/`。

| 文件 | 内容 |
|---|---|
| 01-home.png | 主页与题目辅导入口 |
| 02-tutor-opening.png | AI 开场、面积知识卡片与条件 |
| 03-tutor-complete.png | 三阶段辅导完成与小笔记 |
| 04-practice.png | 第一题专项练习答对 |
| 05-practice-consolidated.png | 连续三题后的初步巩固 |
| 06-learning.png | 一条辅导记录时的学习档案 |
| 07-history-dialogue.png | 完整师生对话回放 |
| 08-homework-review.png | 学生作业、订正与反思 |
| 09-ocr-import.png | 三道照片题的待校对清单 |
| 10-shop.png | 学习档案中的商店和活力 |
| 11-pet-play.png | 玩具购买与限时互动 |
| 12-pet-chat.png | 宠物学习对话入口 |
| 13-pet-hats.png | 娱乐档案的帽子换装 |
| 13b-pet-actions.png | 娱乐档案的动作表演 |
| 13c-pet-feed.png | 娱乐档案的食物互动 |
| 14-learning-updated.png | 两种辅导状态、知识点状态与每日汇总 |
| 15-notes-mistakes.png | 错题筛选与历史作答 |
| 16-visual-tutor.png | 轴对称配图、核验依据与看图老师 |

## 重新运行

在项目根目录执行，继续使用独立演示数据库：

```powershell
python -X utf8 tools/run_product_demo.py
```

如果 8000 端口已由本演示占用，直接打开网页；端口被其他程序使用时可指定其他端口：

```powershell
python -X utf8 tools/run_product_demo.py --port 8001
```

实际调用产品并保存示例运行证据：

```powershell
python -X utf8 tools/capture_product_demo.py ocr
python -X utf8 tools/capture_product_demo.py homework
python -X utf8 tools/capture_product_demo.py tutor-review
python -X utf8 tools/capture_product_demo.py visual
python -X utf8 tools/capture_product_demo.py cli
python -X utf8 tools/capture_product_demo.py snapshot
```

如更换端口，为采集命令追加 `--base-url http://127.0.0.1:8001`。这些命令用于独立演示服务，会新增或更新示例记录。`visual` 使用项目既有的 `.pet-qa/homework-vision/question-2.png` 作为配图输入。

## 证据与验证范围

`ocr-evidence.json`、`homework-evidence.json`、`tutor-review-evidence.json`、`visual-evidence.json`、`snapshot-evidence.json` 保留实际接口输入、输出和耗时；`terminal-demo.txt` 保留终端输出。浏览器操作截图为实际产品画面。

本次验证了上表中的主要功能路径，新增 Python 演示工具已通过语法编译检查。本次没有执行完整自动化回归，不将历史回归数量作为当前版本的验证结果。

本次仅在本机浏览器运行，未验证手机真机、局域网二维码可达性或多用户并发。当前监听 `127.0.0.1`；若需手机访问，另行按实际局域网配置 `--host 0.0.0.0`、服务地址及网络规则。长期学习效果、复杂手写／排版识别和所有题型的反馈质量，需要另行评估。
