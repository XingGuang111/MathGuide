# MathGuide 小学数学启发式辅导 Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个本地终端运行的小学数学启发式辅导 Agent：Ollama 本地小模型 + RapidOCR 拍照搜题 + SQLite 公式库/错题记录 + 苏格拉底式多轮对话。

**Architecture:** 纯 Python 分层结构——表现层 main.py（REPL），业务层 agent.py（状态机）+ knowledge.py（公式库），适配层 llm.py（Ollama 封装）+ ocr.py（RapidOCR 懒加载）+ db.py（SQLite），提示词独立在 prompts.py。LLM 只负责自然语言理解/生成，公式一律查表，杜绝幻觉。

**Tech Stack:** Python 3.12、Ollama（qwen2.5:1.5b）、ollama Python SDK、rapidocr_onnxruntime、sqlite3（标准库）、pytest。

**设计依据:** [2026-10-08-mathguide-agent-design.md](../specs/2026-10-08-mathguide-agent-design.md)

## Global Constraints

- 所有源码文件以 UTF-8 编码、中文注释/提示；终端输出使用中文
- 模型名常量：`MODEL_NAME = "qwen2.5:1.5b"`（config.py）
- 单题最大引导轮数：`MAX_GUIDE_ROUNDS = 12`（config.py）
- 题型限定 6 类：计算题 / 几何应用题 / 行程应用题 / 百分数应用题 / 单位换算题 / 平均数应用题
- 辅导状态标记：`[CONTINUE]` / `[UNDERSTOOD]`，标记行不展示给学生
- 所有 db 函数接受可选 `db_path` 参数（默认 `config.DB_PATH`），测试用临时库
- 所有外部调用（ollama / RapidOCR）必须可 mock：禁止在模块导入期初始化外部资源
- requirements.txt 仅含运行依赖：`ollama`、`rapidocr_onnxruntime`；pytest 为开发依赖（requirements-dev.txt）
- 项目当前不是 git 仓库：Task 1 执行 `git init` 后再开始提交

---

### Task 1: 项目骨架 + config.py

**Files:**
- Create: `config.py`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `data/.gitkeep`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: 全局常量 `MODEL_NAME, DB_PATH, FORMULAS_JSON, MAX_GUIDE_ROUNDS, ANALYZE_RETRY, OCR_IMAGE_EXTS, QUESTION_TYPES`（后续所有任务依赖）

- [ ] **Step 1: 初始化 git 仓库并创建骨架**

```bash
cd "d:/笔记/python程序/MathGuide"
git init
mkdir -p data tests
```

- [ ] **Step 2: 写 config.py**

```python
# -*- coding: utf-8 -*-
"""MathGuide 全局配置常量"""

# 本地大模型（Ollama），可改 "qwen2.5:3b" 获得更好效果
MODEL_NAME = "qwen2.5:1.5b"

# 数据文件路径
DB_PATH = "data/mathguide.db"
FORMULAS_JSON = "data/formulas.json"

# 单题最大引导轮数，超过则兜底讲解，防止无限对话
MAX_GUIDE_ROUNDS = 12

# 题目分析 JSON 解析失败重试次数
ANALYZE_RETRY = 1

# OCR 支持的图片扩展名（小写）
OCR_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}

# 题型枚举（README 定稿 6 类）
QUESTION_TYPES = [
    "计算题",
    "几何应用题",
    "行程应用题",
    "百分数应用题",
    "单位换算题",
    "平均数应用题",
]
```

- [ ] **Step 3: 写 requirements.txt / requirements-dev.txt / .gitignore / tests/__init__.py**

requirements.txt：
```
ollama>=0.3.0
rapidocr_onnxruntime>=1.3.0
```

requirements-dev.txt：
```
-r requirements.txt
pytest>=8.0
```

.gitignore：
```
__pycache__/
*.pyc
.pytest_cache/
data/mathguide.db
```

tests/__init__.py：空文件。

- [ ] **Step 4: 安装依赖并验证导入**

```bash
pip install -r requirements-dev.txt
python -c "import config; print(config.MODEL_NAME)"
```
预期输出：`qwen2.5:1.5b`

- [ ] **Step 5: Commit**

```bash
git add config.py requirements.txt requirements-dev.txt .gitignore tests/__init__.py data/.gitkeep docs/
git commit -m "chore: 项目骨架与全局配置"
```

---

### Task 2: db.py + 50 条公式数据（data/formulas.json）

**Files:**
- Create: `db.py`
- Create: `data/formulas.json`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `config.DB_PATH`, `config.FORMULAS_JSON`
- Produces（后续任务依赖的函数签名）:
  - `init_db(db_path: str | None = None) -> None` — 建表（幂等）+ 空库时从 formulas.json 导入公式与别名
  - `get_all_formulas(db_path=None) -> list[dict]` — `[{"id":1,"knowledge_point":..,"formula":..,"easy_tip":..}, ...]` 按 id 升序
  - `get_formula_by_id(kp_id: int, db_path=None) -> dict | None`
  - `find_formula_by_alias(name: str, db_path=None) -> dict | None` — 别名精确查 → LIKE 包含查，返回公式行
  - `save_record(record: dict, db_path=None) -> int` — 返回新行 id；record 键：session_id, record_date, question_type, question_text, knowledge_point, formula, dialogue_log(str), understood(int)
  - `query_history(date: str | None = None, qtype: str | None = None, db_path=None) -> list[dict]` — 按 create_time 降序
  - `weak_stats(db_path=None) -> list[dict]` — `[{"knowledge_point":.., "total":n, "not_understood":m}]` 按 not_understood 降序、total 降序

- [ ] **Step 1: 写公式数据 data/formulas.json**

完整 50 条（数组，字段：id / knowledge_point / formula / easy_tip / aliases）：

```json
[
  {"id": 1, "knowledge_point": "加法交换律和结合律", "formula": "a+b=b+a；(a+b)+c=a+(b+c)", "easy_tip": "凑整优先：能凑成整十整百的先加", "aliases": ["加法运算律", "加法简便计算"]},
  {"id": 2, "knowledge_point": "乘法交换律和结合律", "formula": "a×b=b×a；(a×b)×c=a×(b×c)", "easy_tip": "见到25找4，见到125找8", "aliases": ["乘法运算律"]},
  {"id": 3, "knowledge_point": "乘法分配律", "formula": "(a+b)×c=a×c+b×c", "easy_tip": "括号里每一项都要乘，别漏乘；反过来用可以简便计算", "aliases": ["分配律", "乘法分配率"]},
  {"id": 4, "knowledge_point": "减法的运算性质", "formula": "a-b-c=a-(b+c)", "easy_tip": "连续减去两个数等于减去它们的和", "aliases": ["连减性质"]},
  {"id": 5, "knowledge_point": "除法的运算性质", "formula": "a÷b÷c=a÷(b×c)", "easy_tip": "连续除以两个数等于除以它们的积", "aliases": ["连除性质"]},
  {"id": 6, "knowledge_point": "四则混合运算顺序", "formula": "先乘除后加减，有括号先算括号里面的", "easy_tip": "同级运算从左往右算，别跳步", "aliases": ["运算顺序", "混合运算"]},
  {"id": 7, "knowledge_point": "有余数的除法", "formula": "被除数=商×除数+余数（余数<除数）", "easy_tip": "余数一定比除数小，可用这个检查结果", "aliases": ["带余除法"]},
  {"id": 8, "knowledge_point": "分数的加减法", "formula": "同分母：分母不变分子相加减；异分母：先通分再计算", "easy_tip": "结果要约成最简分数", "aliases": ["分数加减", "通分"]},
  {"id": 9, "knowledge_point": "分数乘法", "formula": "分子乘分子，分母乘分母，能约分先约分", "easy_tip": "整数看成 分母为1的分数", "aliases": ["分数乘分数"]},
  {"id": 10, "knowledge_point": "分数除法", "formula": "除以一个分数=乘它的倒数", "easy_tip": "别忘把除数倒过来，被除数不变", "aliases": ["倒数", "分数除以分数"]},
  {"id": 11, "knowledge_point": "长方形周长", "formula": "长方形周长=(长+宽)×2", "easy_tip": "周长是长度单位（米、厘米），别写成面积单位", "aliases": ["矩形周长"]},
  {"id": 12, "knowledge_point": "长方形面积", "formula": "长方形面积=长×宽", "easy_tip": "注意区分周长和面积：周长用加法，面积用乘法；面积带平方单位", "aliases": ["矩形面积", "长方形的面积"]},
  {"id": 13, "knowledge_point": "正方形周长", "formula": "正方形周长=边长×4", "easy_tip": "4条边一样长", "aliases": []},
  {"id": 14, "knowledge_point": "正方形面积", "formula": "正方形面积=边长×边长", "easy_tip": "两个相同的数相乘，别算成边长×4（那是周长）", "aliases": ["正方形的面积"]},
  {"id": 15, "knowledge_point": "平行四边形面积", "formula": "平行四边形面积=底×高", "easy_tip": "高必须垂直于底边，斜边不是高", "aliases": ["平行四边形的面积"]},
  {"id": 16, "knowledge_point": "三角形面积", "formula": "三角形面积=底×高÷2", "easy_tip": "忘记÷2是最常见错误", "aliases": ["三角形的面积"]},
  {"id": 17, "knowledge_point": "梯形面积", "formula": "梯形面积=(上底+下底)×高÷2", "easy_tip": "先算括号里的和，再乘高，最后÷2", "aliases": ["梯形的面积"]},
  {"id": 18, "knowledge_point": "圆的周长", "formula": "圆的周长=π×直径=2×π×半径（π取3.14）", "easy_tip": "看清给的是半径还是直径", "aliases": ["圆周长", "圆形周长"]},
  {"id": 19, "knowledge_point": "圆的面积", "formula": "圆的面积=π×半径²（π取3.14）", "easy_tip": "半径²是半径×半径，不是半径×2", "aliases": ["圆面积", "圆形面积"]},
  {"id": 20, "knowledge_point": "长方体表面积", "formula": "长方体表面积=(长×宽+长×高+宽×高)×2", "easy_tip": "无盖盒子少算一个面，注意题目要求", "aliases": ["长方体的表面积"]},
  {"id": 21, "knowledge_point": "长方体体积", "formula": "长方体体积=长×宽×高", "easy_tip": "体积用立方单位", "aliases": ["长方体的体积"]},
  {"id": 22, "knowledge_point": "正方体表面积", "formula": "正方体表面积=棱长×棱长×6", "easy_tip": "6个面完全相同", "aliases": ["正方体的表面积"]},
  {"id": 23, "knowledge_point": "正方体体积", "formula": "正方体体积=棱长×棱长×棱长", "easy_tip": "棱长³是三个棱长相乘", "aliases": ["正方体的体积"]},
  {"id": 24, "knowledge_point": "三角形内角和", "formula": "三角形三个内角的和=180°", "easy_tip": "知道两个角求第三个角用减法", "aliases": ["内角和"]},
  {"id": 25, "knowledge_point": "路程速度时间", "formula": "路程=速度×时间；速度=路程÷时间；时间=路程÷速度", "easy_tip": "注意单位统一（千米/小时配小时）", "aliases": ["行程问题", "路程公式"]},
  {"id": 26, "knowledge_point": "相遇问题", "formula": "相遇时间=总路程÷速度和", "easy_tip": "两人相向而行，每小时共走近的是速度和", "aliases": ["相向而行"]},
  {"id": 27, "knowledge_point": "追及问题", "formula": "追及时间=路程差÷速度差", "easy_tip": "同向而行用速度差，别加成速度和", "aliases": ["同向而行"]},
  {"id": 28, "knowledge_point": "火车过桥问题", "formula": "过桥行驶的总路程=桥长+车长", "easy_tip": "从车头上桥到车尾离桥，别忘加车身长度", "aliases": ["火车过隧道"]},
  {"id": 29, "knowledge_point": "平均速度", "formula": "平均速度=总路程÷总时间", "easy_tip": "不能用两个速度直接平均", "aliases": ["往返平均速度"]},
  {"id": 30, "knowledge_point": "流水行船问题", "formula": "顺水速度=船速+水速；逆水速度=船速-水速", "easy_tip": "先分清顺水还是逆水", "aliases": ["行船问题"]},
  {"id": 31, "knowledge_point": "折扣问题", "formula": "现价=原价×折扣（八折=80%=0.8）", "easy_tip": "八折是按原价的80%出售，不是便宜80%", "aliases": ["打折", "折扣"]},
  {"id": 32, "knowledge_point": "求一个数的百分之几", "formula": "部分量=单位“1”的量×百分率", "easy_tip": "先找准单位“1”是哪个量", "aliases": ["百分数乘法"]},
  {"id": 33, "knowledge_point": "已知百分之几求整体", "formula": "单位“1”的量=对应部分量÷对应百分率", "easy_tip": "量和率要对应：哪部分的量就除以哪部分的率", "aliases": ["百分数除法", "量率对应"]},
  {"id": 34, "knowledge_point": "百分数与小数互化", "formula": "小数→百分数：小数点右移两位加%；百分数→小数：去%小数点左移两位", "easy_tip": "0.8=80%，0.08=8%，别混淆", "aliases": ["百分数化小数"]},
  {"id": 35, "knowledge_point": "合格率与出勤率", "formula": "合格率=合格数÷总数×100%；出勤率=出勤人数÷总人数×100%", "easy_tip": "最后别忘乘100%", "aliases": ["百分率", "发芽率"]},
  {"id": 36, "knowledge_point": "利息问题", "formula": "利息=本金×利率×时间", "easy_tip": "利率是年利率时，时间要按年算", "aliases": ["存款利息"]},
  {"id": 37, "knowledge_point": "成数问题", "formula": "几成=十分之几=百分之几十（二成=20%）", "easy_tip": "“增产二成”是在原来基础上增加20%", "aliases": ["成数"]},
  {"id": 38, "knowledge_point": "浓度问题", "formula": "浓度=溶质÷溶液×100%（溶液=溶质+溶剂）", "easy_tip": "盐水=盐+水，分母是总重量", "aliases": ["盐水问题"]},
  {"id": 39, "knowledge_point": "长度单位换算", "formula": "1千米=1000米；1米=10分米=100厘米=1000毫米", "easy_tip": "千米化米乘1000，米化千米除以1000", "aliases": ["长度单位", "千米和米"]},
  {"id": 40, "knowledge_point": "面积单位换算", "formula": "1平方米=100平方分米=10000平方厘米；1公顷=10000平方米；1平方千米=100公顷", "easy_tip": "相邻面积单位进率是100，不是10", "aliases": ["面积单位", "公顷"]},
  {"id": 41, "knowledge_point": "体积容积单位换算", "formula": "1立方米=1000立方分米；1立方分米=1000立方厘米；1升=1立方分米=1000毫升", "easy_tip": "相邻体积单位进率是1000", "aliases": ["体积单位", "升和毫升"]},
  {"id": 42, "knowledge_point": "质量单位换算", "formula": "1吨=1000千克；1千克=1000克", "easy_tip": "吨、千克、克相邻进率都是1000", "aliases": ["重量单位", "质量单位"]},
  {"id": 43, "knowledge_point": "时间单位换算", "formula": "1时=60分；1分=60秒；1日=24时", "easy_tip": "时间进率是60，不是100", "aliases": ["时间单位", "时分秒"]},
  {"id": 44, "knowledge_point": "年月日", "formula": "1年=12个月；大月31天，小月30天；平年2月28天，闰年2月29天", "easy_tip": "一三五七八十腊，三十一天永不差", "aliases": ["年月日", "平年闰年"]},
  {"id": 45, "knowledge_point": "人民币单位换算", "formula": "1元=10角；1角=10分；1元=100分", "easy_tip": "用小数表示：3角=0.3元", "aliases": ["元角分"]},
  {"id": 46, "knowledge_point": "单位换算方法", "formula": "大单位化小单位×进率；小单位化大单位÷进率", "easy_tip": "先想清进率是多少，再决定乘还是除", "aliases": ["单位换算", "名数改写"]},
  {"id": 47, "knowledge_point": "平均数", "formula": "平均数=总数量÷总份数", "easy_tip": "总数量和总份数要对应同一组数据", "aliases": ["求平均数", "平均分"]},
  {"id": 48, "knowledge_point": "由平均数求总数", "formula": "总数量=平均数×总份数", "easy_tip": "常用于先求总数再求未知的一项", "aliases": ["平均数求总数"]},
  {"id": 49, "knowledge_point": "移多补少", "formula": "多的部分拿出来补给少的，使各部分相等", "easy_tip": "适合数据较少时直观理解平均数", "aliases": []},
  {"id": 50, "knowledge_point": "加法式体重组", "formula": "已知几科平均分求某科：先算总分，再减去已知各科", "easy_tip": "总分=平均分×科数，这是第一步", "aliases": ["平均数应用"]}
]
```

- [ ] **Step 2: 写失败测试 tests/test_db.py**

```python
# -*- coding: utf-8 -*-
import db
import config


def test_init_db_creates_tables_and_imports_formulas(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    rows = db.get_all_formulas(p)
    assert len(rows) == 50
    assert rows[11]["knowledge_point"] == "长方形面积"
    assert "formula" in rows[11] and "easy_tip" in rows[11]


def test_init_db_is_idempotent(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    db.init_db(p)  # 第二次调用不应重复导入
    assert len(db.get_all_formulas(p)) == 50


def test_get_formula_by_id(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    row = db.get_formula_by_id(12, p)
    assert row["knowledge_point"] == "长方形面积"
    assert db.get_formula_by_id(999, p) is None


def test_find_formula_by_alias_exact(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    row = db.find_formula_by_alias("矩形面积", p)  # "长方形面积"的别名
    assert row["knowledge_point"] == "长方形面积"


def test_find_formula_by_alias_fuzzy(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    row = db.find_formula_by_alias("圆的周长公式", p)  # 精确查不到，LIKE 命中"圆的周长"
    assert row["knowledge_point"] == "圆的周长"


def test_save_and_query_record(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    rid = db.save_record({
        "session_id": "s1",
        "record_date": "2026-10-08",
        "question_type": "几何应用题",
        "question_text": "长方形花园长12米宽8米",
        "knowledge_point": "长方形面积",
        "formula": "长方形面积=长×宽",
        "dialogue_log": '[{"role":"student","content":"96"}]',
        "understood": 1,
    }, p)
    assert isinstance(rid, int)
    rows = db.query_history(date="2026-10-08", db_path=p)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
    assert db.query_history(qtype="几何应用题", db_path=p)[0]["id"] == rid
    assert db.query_history(qtype="行程应用题", db_path=p) == []


def test_weak_stats(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    for i, u in enumerate([1, 0, 0]):
        db.save_record({
            "session_id": f"s{i}", "record_date": "2026-10-08",
            "question_type": "几何应用题", "question_text": "t",
            "knowledge_point": "长方形面积", "formula": "f",
            "dialogue_log": "[]", "understood": u,
        }, p)
    db.save_record({
        "session_id": "s9", "record_date": "2026-10-08",
        "question_type": "计算题", "question_text": "t",
        "knowledge_point": "乘法分配律", "formula": "f",
        "dialogue_log": "[]", "understood": 0,
    }, p)
    stats = db.weak_stats(p)
    assert stats[0]["knowledge_point"] == "长方形面积"
    assert stats[0]["total"] == 3
    assert stats[0]["not_understood"] == 2
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest tests/test_db.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'db'`

- [ ] **Step 4: 实现 db.py**

```python
# -*- coding: utf-8 -*-
"""SQLite 数据访问层：公式库、别名表、学习记录"""
import json
import sqlite3
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS math_formula (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_point TEXT UNIQUE,
    formula TEXT,
    easy_tip TEXT
);
CREATE TABLE IF NOT EXISTS kp_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_name TEXT UNIQUE,
    standard_kp TEXT,
    FOREIGN KEY (standard_kp) REFERENCES math_formula(knowledge_point)
);
CREATE TABLE IF NOT EXISTS study_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    record_date TEXT,
    question_type TEXT,
    question_text TEXT,
    knowledge_point TEXT,
    formula TEXT,
    dialogue_log TEXT,
    understood INTEGER,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _conn(db_path=None):
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """建表（幂等）；公式表为空时从 formulas.json 导入公式与别名"""
    with _conn(db_path) as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM math_formula").fetchone()["c"]
        if count == 0:
            with open(config.FORMULAS_JSON, encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                conn.execute(
                    "INSERT INTO math_formula(id, knowledge_point, formula, easy_tip) VALUES (?,?,?,?)",
                    (it["id"], it["knowledge_point"], it["formula"], it["easy_tip"]),
                )
                for alias in it.get("aliases", []):
                    conn.execute(
                        "INSERT INTO kp_alias(alias_name, standard_kp) VALUES (?,?)",
                        (alias, it["knowledge_point"]),
                    )


def get_all_formulas(db_path=None):
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, knowledge_point, formula, easy_tip FROM math_formula ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_formula_by_id(kp_id, db_path=None):
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, knowledge_point, formula, easy_tip FROM math_formula WHERE id=?",
            (kp_id,),
        ).fetchone()
    return dict(row) if row else None


def find_formula_by_alias(name, db_path=None):
    """别名精确查 → LIKE 包含查，命中后返回对应公式行；未命中返回 None"""
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT standard_kp FROM kp_alias WHERE alias_name=?", (name,)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT standard_kp FROM kp_alias WHERE ? LIKE '%' || alias_name || '%' LIMIT 1",
                (name,),
            ).fetchone()
        if row is None:
            return None
        formula = conn.execute(
            "SELECT id, knowledge_point, formula, easy_tip FROM math_formula WHERE knowledge_point=?",
            (row["standard_kp"],),
        ).fetchone()
    return dict(formula) if formula else None


def save_record(record, db_path=None):
    """写入一条学习记录，返回新行 id"""
    with _conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO study_record
               (session_id, record_date, question_type, question_text,
                knowledge_point, formula, dialogue_log, understood)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                record["session_id"], record["record_date"], record["question_type"],
                record["question_text"], record["knowledge_point"], record["formula"],
                record["dialogue_log"], record["understood"],
            ),
        )
        return cur.lastrowid


def query_history(date=None, qtype=None, db_path=None):
    sql = "SELECT * FROM study_record"
    conds, params = [], []
    if date:
        conds.append("record_date=?")
        params.append(date)
    if qtype:
        conds.append("question_type=?")
        params.append(qtype)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY create_time DESC"
    with _conn(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def weak_stats(db_path=None):
    """按知识点统计：总练习数与未独立理解数，按未理解数降序"""
    with _conn(db_path) as conn:
        rows = conn.execute(
            """SELECT knowledge_point,
                      COUNT(*) AS total,
                      SUM(CASE WHEN understood=0 THEN 1 ELSE 0 END) AS not_understood
               FROM study_record
               GROUP BY knowledge_point
               ORDER BY not_understood DESC, total DESC"""
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_db.py -v
```
预期：7 passed

- [ ] **Step 6: Commit**

```bash
git add db.py data/formulas.json tests/test_db.py
git commit -m "feat: SQLite 数据层与 50 条小学公式知识库"
```

---

### Task 3: knowledge.py 公式知识库查询

**Files:**
- Create: `knowledge.py`
- Test: `tests/test_knowledge.py`

**Interfaces:**
- Consumes: `db.get_all_formulas`, `db.get_formula_by_id`, `db.find_formula_by_alias`
- Produces:
  - `load_candidates(db_path=None) -> str` — `"1. 加法交换律和结合律 | 2. 乘法交换律和结合律 | ..."`（单行、id 与知识点名）
  - `get_by_id(kp_id: int, db_path=None) -> dict | None` — 透传 db 查询
  - `resolve(kp_id: int | None, raw_name: str | None, db_path=None) -> dict | None` — 先按 id 查，失败再按 raw_name 别名兜底

- [ ] **Step 1: 写失败测试 tests/test_knowledge.py**

```python
# -*- coding: utf-8 -*-
import db
import knowledge


def _setup(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p


def test_load_candidates_format(tmp_path):
    p = _setup(tmp_path)
    s = knowledge.load_candidates(p)
    assert s.startswith("1. 加法交换律和结合律")
    assert "12. 长方形面积" in s
    assert "50. 加法式体重组" in s
    assert "\n" not in s  # 单行注入提示词


def test_get_by_id(tmp_path):
    p = _setup(tmp_path)
    row = knowledge.get_by_id(12, p)
    assert row["formula"] == "长方形面积=长×宽"
    assert knowledge.get_by_id(None, p) is None
    assert knowledge.get_by_id(0, p) is None


def test_resolve_prefers_id(tmp_path):
    p = _setup(tmp_path)
    row = knowledge.resolve(19, "不相关名字", p)
    assert row["knowledge_point"] == "圆的面积"


def test_resolve_alias_fallback(tmp_path):
    p = _setup(tmp_path)
    row = knowledge.resolve(999, "矩形面积", p)  # id 无效 → 别名兜底
    assert row["knowledge_point"] == "长方形面积"


def test_resolve_returns_none_when_no_match(tmp_path):
    p = _setup(tmp_path)
    assert knowledge.resolve(None, None, p) is None
    assert knowledge.resolve(999, "不存在的知识点", p) is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_knowledge.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'knowledge'`

- [ ] **Step 3: 实现 knowledge.py**

```python
# -*- coding: utf-8 -*-
"""公式知识库查询：编号候选列表 + 按 id 查询 + 别名兜底"""
import db


def load_candidates(db_path=None):
    """构建编号候选列表（单行），注入分析提示词，让模型选编号而非编名称"""
    rows = db.get_all_formulas(db_path)
    return " | ".join(f"{r['id']}. {r['knowledge_point']}" for r in rows)


def get_by_id(kp_id, db_path=None):
    """按编号取公式行；无效 id 返回 None"""
    if not isinstance(kp_id, int) or kp_id <= 0:
        return None
    return db.get_formula_by_id(kp_id, db_path)


def resolve(kp_id, raw_name, db_path=None):
    """先按 id 精确查；失败则用模型输出的原始名称走别名表兜底"""
    row = get_by_id(kp_id, db_path)
    if row is not None:
        return row
    if raw_name:
        return db.find_formula_by_alias(raw_name, db_path)
    return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_knowledge.py -v
```
预期：5 passed

- [ ] **Step 5: Commit**

```bash
git add knowledge.py tests/test_knowledge.py
git commit -m "feat: 公式知识库查询（编号候选+别名兜底）"
```

---

### Task 4: prompts.py 提示词模块

**Files:**
- Create: `prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: `config.QUESTION_TYPES`
- Produces:
  - `build_analyze_prompt(question_text: str, candidates: str) -> str` — 返回完整分析提示词（含候选编号、题型枚举、JSON 输出契约、非数学拒绝规则）
  - `build_tutor_system_prompt(question_text: str, card: dict | None) -> str` — card 键：knowledge_point/formula/easy_tip；card 为 None 时省略公式段
  - 常量 `TAG_CONTINUE = "[CONTINUE]"`、`TAG_UNDERSTOOD = "[UNDERSTOOD]"`

- [ ] **Step 1: 写失败测试 tests/test_prompts.py**

```python
# -*- coding: utf-8 -*-
import prompts


def test_analyze_prompt_contains_contract():
    p = prompts.build_analyze_prompt("长方形面积题", "1. 加法 | 12. 长方形面积")
    assert "长方形面积题" in p            # 题干注入
    assert "12. 长方形面积" in p          # 候选列表注入
    assert "is_elementary_math" in p      # JSON 契约
    assert "knowledge_id" in p
    assert "question_type" in p
    for qt in ["计算题", "几何应用题", "行程应用题", "百分数应用题", "单位换算题", "平均数应用题"]:
        assert qt in p                     # 题型枚举完整


def test_tutor_prompt_rules_and_tags():
    card = {"knowledge_point": "长方形面积", "formula": "长方形面积=长×宽", "easy_tip": "区分周长面积"}
    p = prompts.build_tutor_system_prompt("题目文本", card)
    assert "题目文本" in p
    assert "长方形面积=长×宽" in p
    assert "区分周长面积" in p
    assert prompts.TAG_CONTINUE in p
    assert prompts.TAG_UNDERSTOOD in p
    assert "严禁" in p or "禁止" in p      # 不许直接给答案的铁律
    assert "一个" in p                     # 每次只问一个问题


def test_tutor_prompt_without_card():
    p = prompts.build_tutor_system_prompt("题目文本", None)
    assert "题目文本" in p
    assert "公式" not in p.split("规则")[0]  # 无公式段落
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_prompts.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'prompts'`

- [ ] **Step 3: 实现 prompts.py**

```python
# -*- coding: utf-8 -*-
"""全部提示词（与代码分离，便于调优）"""
import config

TAG_CONTINUE = "[CONTINUE]"
TAG_UNDERSTOOD = "[UNDERSTOOD]"

_ANALYZE_TEMPLATE = """你是小学数学题分类器。请分析下面的题目，只输出 JSON，不要输出任何其他内容。

【题目】
{question}

【候选知识点】（knowledge_id 必须从下列编号中选一个最匹配的，不要自己编名称）
{candidates}

【题型枚举】（question_type 必须六选一）
{qtypes}

【输出 JSON 格式】
{{"is_elementary_math": true, "knowledge_id": 12, "question_type": "几何应用题"}}

【规则】
1. 如果题目不是小学数学内容（例如作文、英语、中学及以上数学、闲聊），输出 {{"is_elementary_math": false, "knowledge_id": null, "question_type": null}}
2. knowledge_id 必须来自候选列表的编号
3. 只输出一行 JSON"""

_TUTOR_TEMPLATE = """你是一位耐心、爱鼓励的小学数学老师，正在用苏格拉底式方法辅导一名小学生。你不替他做题，只用一个个小问题引导他自己想出答案。

【学生不会的题目】
{question}
{card_section}
【教学规则】
1. 严禁直接说出最终答案，严禁给出完整算式的计算结果。即使学生要求，也只能引导。
2. 每次只问一个引导性小问题，问题要短、要具体，符合小学生的理解水平。
3. 学生答错时，先肯定他思路里对的部分，再换个更简单的问题提示，禁止批评。
4. 学生答对一步就夸一句，然后继续问下一步。
5. 不要自己做多步复杂计算，重点是引导学生理清思路。
6. 每轮回复的语言要口语化、亲切，可以用"我们""你"这样的称呼。

【输出格式】
每轮回复的最后另起一行，只输出一个标记：
- 学生还需要继续引导，输出 {tag_continue}
- 学生已经独立推导出正确答案，输出 {tag_understood}
标记单独占一行，不要放在句子里。"""

_CARD_SECTION = """【本题对应的知识点】{knowledge_point}
【核心公式】{formula}
【学生易错点】{easy_tip}
"""


def build_analyze_prompt(question_text, candidates):
    """构建题目分析提示词：题干 + 编号候选 + 题型枚举 + JSON 契约"""
    return _ANALYZE_TEMPLATE.format(
        question=question_text,
        candidates=candidates,
        qtypes="、".join(config.QUESTION_TYPES),
    )


def build_tutor_system_prompt(question_text, card):
    """构建辅导系统提示词；card 为 None 时省略公式段"""
    card_section = _CARD_SECTION.format(**card) if card else ""
    return _TUTOR_TEMPLATE.format(
        question=question_text,
        card_section=card_section,
        tag_continue=TAG_CONTINUE,
        tag_understood=TAG_UNDERSTOOD,
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_prompts.py -v
```
预期：3 passed

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_prompts.py
git commit -m "feat: 分析与辅导提示词模块"
```

---

### Task 5: llm.py Ollama 封装

**Files:**
- Create: `llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `config.MODEL_NAME`、`prompts.build_analyze_prompt`
- Produces:
  - `class LLMError(Exception)`
  - `check_health() -> str | None` — 服务不可达/模型缺失时返回中文提示，正常返回 None
  - `analyze(question_text: str, candidates: str) -> dict` — 返回 `{"is_elementary_math": bool, "knowledge_id": int|None, "question_type": str|None, "raw_knowledge": str|None}`；内部 format="json"，失败重试 `config.ANALYZE_RETRY` 次，仍失败抛 LLMError
  - `chat_stream(messages: list[dict]) -> Iterator[str]` — 逐 chunk yield 文本

- [ ] **Step 1: 写失败测试 tests/test_llm.py（ollama 全部 mock）**

```python
# -*- coding: utf-8 -*-
import json
import pytest
from unittest.mock import patch, MagicMock
import llm


def test_check_health_ok():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.return_value = {"models": [{"name": "qwen2.5:1.5b"}]}
        assert llm.check_health() is None


def test_check_health_service_down():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.side_effect = ConnectionError("refused")
        tip = llm.check_health()
        assert "Ollama" in tip


def test_check_health_model_missing():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.list.return_value = {"models": [{"name": "other:7b"}]}
        tip = llm.check_health()
        assert "ollama pull" in tip


def test_analyze_parses_json():
    payload = {"is_elementary_math": True, "knowledge_id": 12, "question_type": "几何应用题"}
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
        result = llm.analyze("长方形花园", "12. 长方形面积")
    assert result["knowledge_id"] == 12
    assert result["is_elementary_math"] is True


def test_analyze_retries_on_bad_json():
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {"message": {"content": "这不是JSON"}}
        with pytest.raises(llm.LLMError):
            llm.analyze("题目", "候选")
    assert mock_ollama.chat.call_count == 1 + 1  # 首次 + ANALYZE_RETRY 次重试


def test_chat_stream_yields_chunks():
    chunks = [
        {"message": {"content": "我们"}},
        {"message": {"content": "先想想"}},
    ]
    with patch("llm.ollama") as mock_ollama:
        mock_ollama.chat.return_value = iter(chunks)
        out = "".join(llm.chat_stream([{"role": "user", "content": "hi"}]))
    assert out == "我们先想想"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_llm.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'llm'`（注意：不要提前 `import ollama` 失败——llm.py 内 `import ollama` 在文件顶部，依赖已在 Task 1 安装）

- [ ] **Step 3: 实现 llm.py**

```python
# -*- coding: utf-8 -*-
"""Ollama 封装：健康检查、JSON 题目分析、流式对话"""
import json

import ollama

import config
import prompts


class LLMError(Exception):
    """LLM 调用失败（服务不可达 / 输出无法解析）"""


def check_health():
    """启动检查：返回 None 表示正常；否则返回给用户的中文提示"""
    try:
        data = ollama.list()
    except Exception:
        return ("无法连接 Ollama 服务。\n"
                "请先安装 Ollama（https://ollama.com/download）并启动它，然后重试。")
    models = [m.get("name", "") for m in data.get("models", [])]
    if not any(m == config.MODEL_NAME or m.startswith(config.MODEL_NAME) for m in models):
        return (f"本地还没有模型 {config.MODEL_NAME}。\n"
                f"请运行：ollama pull {config.MODEL_NAME}")
    return None


def analyze(question_text, candidates):
    """题目分析：强制 JSON 输出；解析失败重试 ANALYZE_RETRY 次，仍失败抛 LLMError"""
    prompt = prompts.build_analyze_prompt(question_text, candidates)
    last_err = None
    for _ in range(1 + config.ANALYZE_RETRY):
        try:
            resp = ollama.chat(
                model=config.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            data = json.loads(resp["message"]["content"])
            return {
                "is_elementary_math": bool(data.get("is_elementary_math")),
                "knowledge_id": data.get("knowledge_id"),
                "question_type": data.get("question_type"),
                "raw_knowledge": data.get("knowledge_point"),
            }
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            last_err = e
        except Exception as e:
            raise LLMError(f"调用本地大模型失败：{e}") from e
    raise LLMError(f"大模型输出格式异常（已重试{config.ANALYZE_RETRY}次）：{last_err}")


def chat_stream(messages):
    """流式对话：逐 chunk yield 文本。服务异常抛 LLMError"""
    try:
        stream = ollama.chat(model=config.MODEL_NAME, messages=messages, stream=True)
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text
    except Exception as e:
        raise LLMError(f"调用本地大模型失败：{e}") from e
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_llm.py -v
```
预期：6 passed

- [ ] **Step 5: Commit**

```bash
git add llm.py tests/test_llm.py
git commit -m "feat: Ollama 封装（健康检查/JSON分析/流式对话）"
```

---

### Task 6: ocr.py RapidOCR 封装

**Files:**
- Create: `ocr.py`
- Test: `tests/test_ocr.py`

**Interfaces:**
- Consumes: `config.OCR_IMAGE_EXTS`
- Produces:
  - `class OCRError(Exception)` — 文件不存在/格式不支持
  - `recognize(image_path: str) -> str` — 返回清洗后的识别文本；未识别到文字返回 `""`；引擎初始化失败抛 `OCRError`
  - `_clean(lines: list[str]) -> str` — 合并行、去空行、去首尾空白

- [ ] **Step 1: 写失败测试 tests/test_ocr.py**

```python
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
import ocr


def test_recognize_file_not_found():
    with pytest.raises(ocr.OCRError, match="不存在"):
        ocr.recognize("不存在的图片.jpg")


def test_recognize_bad_extension(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ocr.OCRError, match="格式"):
        ocr.recognize(str(f))


def test_recognize_success(tmp_path):
    f = tmp_path / "q.jpg"
    f.write_bytes(b"fake")
    fake_engine = MagicMock()
    fake_engine.return_value = (
        [[None, "一个长方形长12米", 0.99], [None, "宽8米，面积是多少？", 0.98]],
        0.5,
    )
    with patch("ocr._get_engine", return_value=fake_engine):
        text = ocr.recognize(str(f))
    assert text == "一个长方形长12米 宽8米，面积是多少？"


def test_recognize_empty_result(tmp_path):
    f = tmp_path / "q.jpg"
    f.write_bytes(b"fake")
    fake_engine = MagicMock()
    fake_engine.return_value = (None, 0.1)
    with patch("ocr._get_engine", return_value=fake_engine):
        assert ocr.recognize(str(f)) == ""


def test_clean_lines():
    assert ocr._clean(["  3.5千米  ", "", "=多少米？ "]) == "3.5千米 =多少米？"
    assert ocr._clean([]) == ""
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_ocr.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'ocr'`

- [ ] **Step 3: 实现 ocr.py**

```python
# -*- coding: utf-8 -*-
"""RapidOCR 封装：懒加载引擎、图片识别、文本清洗"""
from pathlib import Path

import config


class OCRError(Exception):
    """OCR 不可用（文件不存在/格式不支持/引擎初始化失败）"""


_engine = None  # 懒加载：首次使用时才初始化（导入本模块不占内存）


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        except Exception as e:
            raise OCRError(f"OCR 引擎初始化失败：{e}") from e
    return _engine


def recognize(image_path):
    """识别图片中的题目文字，返回清洗后的单行文本；识别不到返回空串"""
    path = Path(image_path.strip().strip('"'))
    if not path.exists():
        raise OCRError(f"图片不存在：{path}")
    if path.suffix.lower() not in config.OCR_IMAGE_EXTS:
        raise OCRError(f"不支持的图片格式 {path.suffix}，支持：{' '.join(sorted(config.OCR_IMAGE_EXTS))}")
    engine = _get_engine()
    result, _ = engine(str(path))
    if not result:
        return ""
    lines = [item[1] for item in result]
    return _clean(lines)


def _clean(lines):
    """合并识别行：去空白行、去首尾空白，用空格连接为单行题干"""
    return " ".join(line.strip() for line in lines if line and line.strip())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_ocr.py -v
```
预期：5 passed

- [ ] **Step 5: Commit**

```bash
git add ocr.py tests/test_ocr.py
git commit -m "feat: RapidOCR 拍照搜题封装（懒加载+文本清洗）"
```

---

### Task 7: agent.py 辅导状态机

**Files:**
- Create: `agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `llm.analyze`, `llm.chat_stream`, `llm.LLMError`, `knowledge.load_candidates`, `knowledge.resolve`, `prompts.build_tutor_system_prompt`, `prompts.TAG_CONTINUE/TAG_UNDERSTOOD`, `db.save_record`, `config.MAX_GUIDE_ROUNDS`
- Produces:
  - `class AgentState(Enum)` — `IDLE / ANALYZING / FORMULA_SHOWN / GUIDING / DONE`
  - `class TutorAgent(db_path=None)`，属性：`state`、`finished: bool`（本轮辅导是否结束）
  - `start_session(question_text: str) -> dict` — 返回 `{"ok": bool, "card": dict|None, "question_type": str|None, "message": str}`；`ok=False` 时 message 为拒绝/失败提示
  - `reply(student_msg: str) -> Iterator[str]` — 仅在 GUIDING 状态可用；yield 引导回复 chunk（不含标记行）；迭代结束后 `finished` 已更新；结束时会话自动归档
  - `abort() -> None` — 放弃当前题目回 IDLE，不归档

- [ ] **Step 1: 写失败测试 tests/test_agent.py**

```python
# -*- coding: utf-8 -*-
from unittest.mock import patch
import db
import agent as agent_mod


def _new_agent(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return agent_mod.TutorAgent(db_path=p), p


ANALYZE_OK = {"is_elementary_math": True, "knowledge_id": 12,
              "question_type": "几何应用题", "raw_knowledge": None}


def _start_ok(a):
    with patch("agent.llm.analyze", return_value=ANALYZE_OK):
        return a.start_session("长方形花园长12米宽8米，面积是多少？")


def test_start_session_success(tmp_path):
    a, _ = _new_agent(tmp_path)
    r = _start_ok(a)
    assert r["ok"] is True
    assert r["card"]["formula"] == "长方形面积=长×宽"
    assert r["question_type"] == "几何应用题"
    assert a.state == agent_mod.AgentState.FORMULA_SHOWN


def test_start_session_rejects_non_math(tmp_path):
    a, _ = _new_agent(tmp_path)
    with patch("agent.llm.analyze", return_value={
            "is_elementary_math": False, "knowledge_id": None,
            "question_type": None, "raw_knowledge": None}):
        r = a.start_session("帮我写一篇作文")
    assert r["ok"] is False
    assert a.state == agent_mod.AgentState.IDLE


def test_reply_continue_then_understood(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    replies = iter(["那我们想想面积怎么算？[CONTINUE]",
                    "对啦！你自己算出来了！[UNDERSTOOD]"])
    with patch("agent.llm.chat_stream", side_effect=lambda msgs: iter([next(replies)])):
        out1 = "".join(a.reply("不知道"))
        assert "[CONTINUE]" not in out1   # 标记不外泄
        assert a.finished is False
        out2 = "".join(a.reply("12乘8等于96"))
        assert "[UNDERSTOOD]" not in out2
        assert a.finished is True
    assert a.state == agent_mod.AgentState.IDLE  # 归档后回 IDLE
    rows = db.query_history(db_path=p)
    assert len(rows) == 1
    assert rows[0]["understood"] == 1
    assert "12乘8等于96" in rows[0]["dialogue_log"]


def test_max_rounds_fallback(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    a.state = agent_mod.AgentState.GUIDING
    a.rounds = agent_mod.config.MAX_GUIDE_ROUNDS  # 直接置为上限
    with patch("agent.llm.chat_stream", return_value=iter(["再想想？[CONTINUE]"])):
        out = "".join(a.reply("还是不会"))
    assert a.finished is True
    rows = db.query_history(db_path=p)
    assert rows[0]["understood"] == 0  # 超轮数兜底


def test_abort(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    a.abort()
    assert a.state == agent_mod.AgentState.IDLE
    assert db.query_history(db_path=p) == []  # 放弃不归档
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_agent.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: 实现 agent.py**

```python
# -*- coding: utf-8 -*-
"""启发式辅导状态机：分析题目 → 展示公式 → 多轮引导 → 归档"""
import json
import re
import uuid
from datetime import date
from enum import Enum

import config
import db
import knowledge
import llm
import prompts


class AgentState(Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    FORMULA_SHOWN = "FORMULA_SHOWN"
    GUIDING = "GUIDING"
    DONE = "DONE"


_TAG_RE = re.compile(r"\[(CONTINUE|UNDERSTOOD)\]")

_FALLBACK_EXPLAIN = (
    "没关系，我们已经试了很多步啦。老师来讲一下完整的思路："
    "先回忆本题的公式，把题目里的数字对应进去，一步一步计算就能得到答案。"
    "你可以把这道题记下来，过几天再自己试一次！"
)


class TutorAgent:
    def __init__(self, db_path=None):
        self.db_path = db_path
        self.state = AgentState.IDLE
        self.finished = False
        self.session_id = None
        self.question_text = ""
        self.question_type = None
        self.card = None
        self.messages = []       # 发给 LLM 的消息（含 system）
        self.dialogue = []       # 归档用对话日志（student/teacher）
        self.rounds = 0

    # ---------- 会话入口 ----------

    def start_session(self, question_text):
        """分析题目并准备辅导。返回 {"ok","card","question_type","message"}"""
        self.question_text = question_text
        self.session_id = uuid.uuid4().hex
        self.state = AgentState.ANALYZING
        try:
            result = llm.analyze(question_text, knowledge.load_candidates(self.db_path))
        except llm.LLMError as e:
            self.state = AgentState.IDLE
            return {"ok": False, "card": None, "question_type": None, "message": str(e)}
        if not result["is_elementary_math"]:
            self.state = AgentState.IDLE
            return {"ok": False, "card": None, "question_type": None,
                    "message": "这道题好像不是小学数学题哦，我只能辅导小学数学题。"}
        self.card = knowledge.resolve(result["knowledge_id"], result["raw_knowledge"], self.db_path)
        self.question_type = result["question_type"]
        self.messages = [
            {"role": "system", "content": prompts.build_tutor_system_prompt(question_text, self.card)}
        ]
        self.state = AgentState.FORMULA_SHOWN
        return {"ok": True, "card": self.card, "question_type": self.question_type, "message": ""}

    def begin_guiding(self):
        """从 FORMULA_SHOWN 进入 GUIDING，返回 AI 老师的第一个引导问题（generator）"""
        self.state = AgentState.GUIDING
        return self._next_chunk_stream()

    # ---------- 对话 ----------

    def reply(self, student_msg):
        """接收学生回答，yield AI 引导回复 chunk（不含状态标记）。
        迭代结束后 finished 已更新；结束时会话自动归档。"""
        if self.state != AgentState.GUIDING:
            raise RuntimeError("当前不在辅导中")
        self.messages.append({"role": "user", "content": student_msg})
        self.dialogue.append({"role": "student", "content": student_msg})
        return self._next_chunk_stream()

    def _next_chunk_stream(self):
        """调 LLM 生成一轮回复：剥离标记后 yield 正文；流结束后按标记推进状态"""
        full = []
        try:
            for chunk in llm.chat_stream(self.messages):
                full.append(chunk)
        except llm.LLMError as e:
            yield f"（老师暂时开小差了：{e}）"
            return
        text = "".join(full)
        m = _TAG_RE.search(text)
        tag = m.group(1) if m else "CONTINUE"
        body = _TAG_RE.sub("", text).strip()
        self.messages.append({"role": "assistant", "content": text})
        self.dialogue.append({"role": "teacher", "content": body})
        self.rounds += 1
        yield body + "\n"
        if tag == "UNDERSTOOD":
            yield "\n太棒了，这道题你自己想明白啦！\n"
            self._archive(understood=1)
        elif self.rounds >= config.MAX_GUIDE_ROUNDS:
            yield "\n" + _FALLBACK_EXPLAIN + "\n"
            self._archive(understood=0)
        self.finished = self.state == AgentState.IDLE

    # ---------- 归档与放弃 ----------

    def _archive(self, understood):
        db.save_record({
            "session_id": self.session_id,
            "record_date": date.today().isoformat(),
            "question_type": self.question_type or "未分类",
            "question_text": self.question_text,
            "knowledge_point": self.card["knowledge_point"] if self.card else "未匹配",
            "formula": self.card["formula"] if self.card else "",
            "dialogue_log": json.dumps(self.dialogue, ensure_ascii=False),
            "understood": understood,
        }, self.db_path)
        self.state = AgentState.IDLE
        self.finished = True

    def abort(self):
        """放弃当前题目，不归档"""
        self.state = AgentState.IDLE
        self.finished = True
        self.messages = []
        self.dialogue = []
```

注意：`reply` 返回 generator，`begin_guiding` 同样返回 generator；`finished` 在 generator 耗尽后有效。`start_session` 成功后由 main 调 `begin_guiding()` 让 AI 先开口。

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_agent.py -v
```
预期：5 passed

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent.py
git commit -m "feat: 启发式辅导状态机（分析-引导-标记-归档）"
```

---

### Task 8: main.py 终端入口

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `llm.check_health`, `db.init_db/query_history/weak_stats`, `agent.TutorAgent`, `ocr.recognize/OCRError`, `config`
- Produces:
  - `parse_command(text: str) -> tuple[str, str | None]` — 返回 (命令名, 参数)；非斜杠输入返回 `("", None)`
  - `main() -> None` — REPL 入口

- [ ] **Step 1: 写失败测试 tests/test_main.py**

```python
# -*- coding: utf-8 -*-
import main


def test_parse_command_plain_text():
    assert main.parse_command("长方形面积题") == ("", None)


def test_parse_command_known():
    assert main.parse_command("/quit") == ("quit", None)
    assert main.parse_command("/photo D:\\错题\\a.jpg") == ("photo", "D:\\错题\\a.jpg")
    assert main.parse_command("/history 2026-10-08") == ("history", "2026-10-08")
    assert main.parse_command("/history") == ("history", None)


def test_parse_command_unknown_falls_back():
    # 未知斜杠命令按普通文本处理（返回空命令名）
    assert main.parse_command("/xyz abc") == ("", None)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_main.py -v
```
预期：FAIL，`ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: 实现 main.py**

```python
# -*- coding: utf-8 -*-
"""MathGuide 终端入口：REPL 循环与命令分发"""
import json
import sys

import agent as agent_mod
import config
import db
import llm
import ocr

KNOWN_COMMANDS = {"photo", "history", "stats", "new", "help", "quit"}

HELP = """可用命令：
  直接输入题目        开始一轮启发式辅导
  /photo 图片路径     拍照搜题（OCR 识别后可修正）
  /history            查看全部历史记录
  /history 日期       按日期查看，如 /history 2026-10-08
  /history 题型       按题型查看，如 /history 几何应用题
  /stats              薄弱知识点统计
  /new                放弃当前题目
  /help               查看本帮助
  /quit               退出"""

_BANNER = f"""{'=' * 50}
  MathGuide 小学数学启发式辅导 (模型: {config.MODEL_NAME})
  直接输入题目开始辅导；拍题用 /photo 图片路径
  /help 查看全部命令
{'=' * 50}"""


def parse_command(text):
    """解析斜杠命令 → (命令名, 参数)；普通输入或未知命令返回 ("", None)"""
    text = text.strip()
    if not text.startswith("/"):
        return "", None
    head, _, arg = text[1:].partition(" ")
    head = head.lower()
    if head not in KNOWN_COMMANDS:
        return "", None
    return head, (arg.strip() or None)


def _print_card(result):
    if result["card"]:
        c = result["card"]
        print(f"\n【知识点】{c['knowledge_point']}  【题型】{result['question_type']}")
        print(f"【公式】{c['formula']}")
        print(f"【易错提示】{c['easy_tip']}\n")
    else:
        print(f"\n【题型】{result['question_type']}（未匹配到公式，直接开始辅导）\n")


def _stream_and_print(chunks):
    print("AI老师> ", end="", flush=True)
    for chunk in chunks:
        print(chunk, end="", flush=True)
    print()


def _handle_photo(tutor, arg):
    if not arg:
        print("用法：/photo 图片路径")
        return
    try:
        text = ocr.recognize(arg)
    except ocr.OCRError as e:
        print(f"OCR 失败：{e}\n也可以直接把题目打字发给我。")
        return
    if not text:
        print("没有识别到文字，请换一张更清晰的印刷体题目照片。")
        return
    print(f"\n【OCR 识别结果】\n{text}")
    print("（直接回车确认，或输入修正后的题目）")
    confirm = input("确认> ").strip()
    question = confirm if confirm else text
    _start_tutoring(tutor, question)


def _start_tutoring(tutor, question):
    result = tutor.start_session(question)
    if not result["ok"]:
        print(result["message"])
        return
    _print_card(result)
    _stream_and_print(tutor.begin_guiding())


def _handle_history(arg):
    date, qtype = None, None
    if arg:
        if len(arg) == 10 and arg[4] == "-" and arg[7] == "-":
            date = arg
        else:
            qtype = arg
    rows = db.query_history(date=date, qtype=qtype)
    if not rows:
        print("没有找到相关记录。")
        return
    for i, r in enumerate(rows, 1):
        mark = "✓独立解出" if r["understood"] else "✗老师讲解"
        print(f"[{i}] {r['record_date']} | {r['question_type']} | {r['knowledge_point']} | {mark}")
        print(f"    {r['question_text'][:40]}")
    sel = input("输入序号查看完整对话（直接回车返回）：").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(rows):
        r = rows[int(sel) - 1]
        print(f"\n【公式】{r['formula']}")
        for msg in json.loads(r["dialogue_log"]):
            who = "你" if msg["role"] == "student" else "AI老师"
            print(f"{who}> {msg['content']}")


def _handle_stats():
    stats = db.weak_stats()
    if not stats:
        print("还没有练习记录。")
        return
    print("\n【薄弱知识点统计】（按未独立掌握次数排序）")
    for s in stats:
        print(f"  {s['knowledge_point']}: 共{s['total']}次, 未独立掌握{s['not_understood']}次")


def main():
    tip = llm.check_health()
    if tip:
        print(tip)
        sys.exit(1)
    db.init_db()
    print(_BANNER)
    tutor = agent_mod.TutorAgent()
    while True:
        try:
            guiding = tutor.state == agent_mod.AgentState.GUIDING
            text = input(("你> " if guiding else "题目> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not text:
            continue
        cmd, arg = parse_command(text)
        if cmd == "quit":
            print("再见！")
            break
        elif cmd == "help":
            print(HELP)
        elif cmd == "new":
            tutor.abort()
            print("好的，换一道题吧。")
        elif cmd == "history":
            _handle_history(arg)
        elif cmd == "stats":
            _handle_stats()
        elif cmd == "photo":
            if guiding:
                print("正在辅导中，先 /new 结束当前题目。")
            else:
                _handle_photo(tutor, arg)
        elif guiding:
            _stream_and_print(tutor.reply(text))
            if tutor.finished:
                print("✔ 本轮辅导已保存")
        else:
            _start_tutoring(tutor, text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_main.py -v
```
预期：3 passed

- [ ] **Step 5: 运行全部测试**

```bash
python -m pytest tests/ -v
```
预期：全部通过（29 个测试）

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: 终端 REPL 入口与命令分发"
```

---

### Task 9: 真机联调 + README 使用说明

**Files:**
- Modify: `README.md`（在原有方案文档末尾追加"精简版运行指南"一节）
- Create: `docs/manual-test.md`（手动测试用例清单）

**Interfaces:**
- Consumes: 全部已完成模块

- [ ] **Step 1: 真机准备（人工执行）**

```bash
# 安装 Ollama 后：
ollama pull qwen2.5:1.5b
python main.py
```
预期：打印启动横幅与 `题目>` 提示符

- [ ] **Step 2: 手动测试用例 docs/manual-test.md**

```markdown
# MathGuide 真机手动测试清单

| # | 输入 | 预期 |
|---|------|------|
| 1 | 25×44 用简便方法计算 | 匹配"乘法交换律和结合律"或"乘法分配律"，全程不直接给答案 |
| 2 | 一个长方形花园长12米宽8米，面积是多少？ | 匹配"长方形面积"，引导后学生答 96 → [UNDERSTOOD] 结束并归档 |
| 3 | 甲乙两地相距300千米，汽车每小时行60千米，几小时到达？ | 匹配"路程速度时间" |
| 4 | 一件商品原价200元，打八折后多少钱？ | 匹配"折扣问题" |
| 5 | 3.5千米等于多少米？ | 匹配"长度单位换算"或"单位换算方法" |
| 6 | 小明三次数学成绩92、88、96，平均分是多少？ | 匹配"平均数" |
| 7 | 帮我写一篇作文 | 礼貌拒绝，不进入辅导 |
| 8 | /photo <印刷体题目图片> | 识别文本 → 确认 → 正常进入辅导 |
| 9 | /photo <不存在路径> | 提示图片不存在，不崩溃 |
| 10 | 连续答错超过 12 轮 | 兜底输出完整讲解，归档 understood=0 |
| 11 | /history / /history 今天日期 / /history 几何应用题 | 正确筛选并可回看对话 |
| 12 | /stats | 按未掌握次数降序展示 |
| 13 | 辅导中 /new | 放弃当前题，不归档 |
| 14 | 关闭 Ollama 后启动程序 | 打印安装/启动提示并退出 |
```

- [ ] **Step 3: README.md 追加精简版运行指南**

在 README.md 末尾追加：

```markdown
---

# 精简版运行指南（已实现代码）

本仓库当前实现了方案中的**精简版终端 Agent**（详见 `docs/superpowers/specs/2026-10-08-mathguide-agent-design.md`）。

## 功能

- 文字输入 或 `/photo 图片路径` 拍照搜题（RapidOCR 离线识别，可人工修正）
- 自动识别知识点与题型，从本地 50 条公式库查表展示（杜绝公式幻觉）
- 苏格拉底式启发对话：AI 老师只提问不给答案，引导学生自己解出
- 自动归档学习记录，支持 `/history` 按日期/题型回看、`/stats` 薄弱知识点统计

## 部署运行

1. 安装 Ollama：https://ollama.com/download
2. `ollama pull qwen2.5:1.5b`（约 1GB；内存充足可改 config.py 用 qwen2.5:3b）
3. `pip install -r requirements.txt`
4. `python main.py`

首次使用 OCR 时 RapidOCR 会自动下载识别模型（约 20MB，一次性）。

## 测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

真机联调清单见 `docs/manual-test.md`。
```

- [ ] **Step 4: 最终全量验证**

```bash
python -m pytest tests/ -v
```
预期：全部通过

- [ ] **Step 5: Commit**

```bash
git add README.md docs/manual-test.md
git commit -m "docs: 精简版运行指南与真机测试清单"
```

---

## Self-Review 记录

- **Spec coverage**：设计文档全部模块（config/db/knowledge/prompts/llm/ocr/agent/main）均有对应任务；50 条公式、6 类题型、状态标记、超轮兜底、OCR 确认流、错误处理表各项均有实现任务；测试策略中的 4 个单元测试文件全部覆盖（test_prompts/test_main 为新增小测试）。
- **Placeholder scan**：所有任务含完整代码与完整 50 条公式数据，无 TBD/TODO。
- **Type consistency**：db 函数签名在 Task 2 定义，Task 3/7/8 消费一致（`db_path` 关键字参数、`resolve(kp_id, raw_name, db_path)`）；`agent.llm.analyze` / `agent.llm.chat_stream` 的 mock 路径与 Task 5 的模块结构一致；`TAG_CONTINUE/UNDERSTOOD` 在 prompts（Task 4）定义、agent（Task 7）使用一致。
- **已知取舍**：`begin_guiding` 在 start_session 成功后由 main 调用一次（AI 先开口），设计文档时序图与此一致。
