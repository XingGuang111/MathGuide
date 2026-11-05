# GitHub 发布完整性检查

本文件供维护者发布时使用。首次使用者按根目录 README 的快速启动操作即可。

## 必须包含的文件

发布完整的项目文件，不能只上传 README 或已被 Git 跟踪的旧文件：

- 根目录全部 Python 模块，包括 `homework*.py`、`pet*.py`、`teaching.py` 等新模块。
- `requirements.txt`、`requirements-dev.txt`、`README.md`、`LICENSE`、`.gitignore`。
- `start.cmd`、`tools/start_web.py` 和 `.gitattributes`：Windows 一键启动入口、浏览器就绪检测与 CMD 换行设置。
- `data/formulas.json`：首次运行初始化数据库所需的公式种子。
- `models/Modelfile.qwen25-mathguide`：从公开模型创建本地辅导模型。
- 完整 `web/`：页面、脚本、样式、宠物动画、商品图片、清单和来源声明。缺少 `web/assets/` 会使服务导入失败。
- `docs/`：尤其是 `system prompt.txt`、`primary_math_tutor.jsonl`、`Dialogue Example.md`，以及 README 链接的文档。
- `tests/` 和 `tools/`：便于复现验证与维护。

不要发布个人数据库、会话快照、学生照片、私人测试记录、虚拟环境和本机缓存。模型权重不随源码上传，使用者按 README 从 Ollama 下载。

## 检查并提交

在项目根目录查看工作区和忽略规则：

```sh
git status --short
git status --short --ignored
```

`??` 表示文件尚未纳入 Git；只使用 `git commit -am` 不会提交这些文件。检查待发布内容后，可以明确添加项目文件：

```sh
git add -- *.py .gitignore .gitattributes start.cmd README.md LICENSE requirements.txt requirements-dev.txt data/formulas.json models web docs tests tools
git diff --cached --stat
git diff --cached --name-only
```

在提交前核对文件清单，确认没有个人数据，并保留根目录代码 `LICENSE`。第三方素材的许可、来源和署名文件须一同保留。

然后按自己的分支发布流程提交和推送。README 更新、代码更新、素材更新应进入同一可用版本，不要仅上传说明文件。

## 上传后的最后验证

1. 从 GitHub 页面重新下载 ZIP，解压到新目录；不要复用本机开发目录或旧数据库。
2. 按 README 创建新的虚拟环境、安装依赖、下载并创建模型。
3. 启动网页，检查 `/api/health` 的 `ok` 为 `true`。
4. 提交 README 中的长方形题并完成一轮对话，确认学习档案出现记录。
5. 上传清晰的测试题图片，确认 OCR 可用；需要配图作业时另验证视觉模型。
6. 确认宠物和商店素材可加载，运行 `python -m pytest -q` 检查自动化测试。

这一步才能验证远端实际发布的内容；本机测试通过不代表未上传的文件已经包含在 GitHub 下载包中。
