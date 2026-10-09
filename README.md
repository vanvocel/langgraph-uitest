# LangGraph-uitest

基于 **Excel → NL → LLM 编译 YAML → POM Discover → Playwright 执行 → Allure + Excel 回填 → 飞书通知** 的 UI 自动化测试框架。

| 阶段 | 是否调大模型 | 说明 |
|------|--------------|------|
| Excel → NL | 否 | 确定性转换（LangGraph 节点） |
| NL → YAML | **是** | compile（LangGraph + LLM） |
| Discover | 可选 | 启发式 + 可选 LLM |
| Run / 回填 / 通知 | 否 | 本地确定性执行 |

用例编写请遵循根目录 [`用例编写标准.md`](用例编写标准.md)。服务器部署见 [`部署方案.md`](部署方案.md)。

---

## 能力概览

| 命令 | 作用 |
|------|------|
| `init` | 创建需求工作区 `runs/<req>/` |
| `excel-to-nl` | Excel → `nl/*.nl.md`（表头兼容 MG0557；无 LLM） |
| `compile` | NL → YAML（LLM）；`--from-excel` 时先 Excel→NL 再编译（LangGraph pipeline） |
| `discover` | YAML 语义元素 → POM 定位器 |
| `run` | 执行用例 + Allure + Excel 回填；`notify` 开启时自动发报告 |
| `notify` | 仅发送已有回填 Excel + 报告链接（不重跑） |
| `excel-backfill` | 仅根据已有 Allure 回填 Excel |

自动执行会跳过：`manual` / `ai_outbound` / `needs_fixture`（或 `meta.manual_only` / `meta.needs_fixture`）。

---

## 目录结构

```
LangGraph-uitest/
├── main.py
├── requirements.txt
├── .env / .env.example
├── 用例编写标准.md          # Excel/NL 怎么写才少失败
├── 部署方案.md              # 服务器 + Nginx + 飞书
├── config/
│   ├── settings.yaml        # 浏览器、登录、excel_backfill、excel_to_nl
│   ├── llm.yaml
│   ├── accounts.yaml
│   └── notify.yaml          # 飞书 / 报告 URL
├── framework/
│   ├── agents/
│   │   ├── excel_nl/        # Excel→NL
│   │   ├── pipeline/        # Excel→NL → compile 串联
│   │   ├── compile/         # NL→YAML（含 lint）
│   │   └── discover/
│   ├── notify/              # 多渠道通知（飞书已实现）
│   ├── runner/              # 执行、Allure、Excel 回填
│   └── ...
├── tests/
└── runs/<req_id>/
    ├── excel/cases.xlsx
    ├── excel_nl.yaml        # page_url / tab / 可选 skip 列表
    ├── nl/*.nl.md
    ├── yaml/*.yaml
    ├── pom/elements.yaml
    ├── bindings/discover.yaml
    ├── allure-report.html
    ├── logs/
    └── <req>_结果回填.xlsx
```

示例需求：`MG0473`（清洗池）、`MG0557`（清洗评分规则）。

---

## 环境准备

### 1. Python 依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 环境变量（`.env`）

复制 `.env.example` 后填写：

```text
# 登录（与 config/accounts.yaml 对应）
TEST_USERNAME=...
TEST_PASSWORD=...

# LLM（compile / discover）
DEEPSEEK_API_KEY=...
# LLM_PROFILE=deepseek

# 飞书通知（可选）
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_CHAT_ID=

# 报告公网根地址（可选；部署后配置）
# REPORT_BASE_URL=https://uitest.example.com/reports
```

### 3. 常用配置

| 文件 | 要点 |
|------|------|
| `config/settings.yaml` | `browser.headless`、`excel_backfill`、`excel_to_nl` |
| `config/llm.yaml` | `backend: llm`、`active` profile（勿随意改 active） |
| `config/notify.yaml` | `enabled`、飞书渠道、`upload_html: false`（用链接） |
| `runs/<req>/excel_nl.yaml` | 该需求的 `page_url` / `tab` |

---

## 标准执行流程（推荐）

以需求号 `MG0557` 为例。写 Excel 前请先读 [`用例编写标准.md`](用例编写标准.md)。

### 步骤 1：初始化（每个需求一次）

```bash
python main.py init --req MG0557
```

### 步骤 2：Excel → NL

1. 放入 `runs/MG0557/excel/cases.xlsx`  
   - 第 2 行表头需含：**用例ID、用例标题、前置条件、测试步骤、预期结果**（与 MG0557 兼容）
2. 编辑 `runs/MG0557/excel_nl.yaml`：

```yaml
page_url: "https://lead.z-niu.com/rule/clean/"
tab: "清洗评分规则"
# 可选：ai_outbound_ids / needs_fixture_ids
```

3. 生成 NL（不必手写）：

```bash
python main.py excel-to-nl --req MG0557
```

说明列或配置中的标记会写入 NL：

- `【人工/AI外呼】` → 自动集 skip（Block）
- `【需造数】` → 自动集 skip（Block）

### 步骤 3：NL → YAML（大模型）

```bash
# 仅编译已有 NL
python main.py compile --req MG0557 --llm deepseek

# 一条龙（LangGraph：Excel→NL → NL→YAML）
python main.py compile --req MG0557 --from-excel --llm deepseek
```

- 输出：`runs/MG0557/yaml/<case_id>.yaml`（同名覆盖）
- 编译后会对「断言页面」等不安全步骤做确定性 lint
- 正式编译禁止 stub；调试可加 `--allow-stub`

### 步骤 4：Discover → POM

```bash
python main.py discover --req MG0557 --force --llm deepseek
# 仅启发式：python main.py discover --req MG0557 --force --no-llm
```

产物：`pom/elements.yaml`、`bindings/discover.yaml`。  
**绑定 POM 必须走项目 discover，禁止助手手写定位器冒充结果。**

### 步骤 5：执行

```bash
python main.py run --req MG0557
python main.py run --req MG0557 -- -q --tb=line
python main.py run --req MG0557 --no-excel-backfill
```

观察浏览器时改 `config/settings.yaml`：`headless: false`，可加大 `slow_mo_ms`。

### 步骤 6：查看结果

| 产物 | 位置 |
|------|------|
| Allure | `runs/MG0557/allure-report.html` |
| Excel 回填 | `runs/MG0557/MG0557_结果回填.xlsx` |
| 日志 | `runs/MG0557/logs/` |

测试结果：**通过** / **失败** / **Block**（人工、造数或未执行）。

### 步骤 7：飞书通知（可选）

`run` 结束后若 `config/notify.yaml` 的 `enabled: true` 会自动发；也可：

```bash
python main.py notify --req MG0557
```

消息含摘要 + 回填 Excel；HTML 过大不上传，改为 **报告链接**（需配置 `REPORT_BASE_URL`，见 [`部署方案.md`](部署方案.md)）。

仅回填不重跑：

```bash
python main.py excel-backfill --req MG0557
```

---

## 命令速查

```bash
python main.py -h

python main.py init --req <REQ>
python main.py excel-to-nl --req <REQ> [--excel PATH] [--page-url URL] [--tab 页签]
python main.py compile --req <REQ> [--llm deepseek] [--from-excel] [--case ID]
python main.py discover --req <REQ> [--force] [--llm deepseek | --no-llm]
python main.py run --req <REQ> [--excel PATH] [--no-excel-backfill] [--smoke] [-- -q]
python main.py notify --req <REQ>
python main.py excel-backfill --req <REQ> [--excel PATH]
```

---

## LangGraph 节点关系（简要）

```text
excel_nl 图:     START → excel_to_nl → END
pipeline 图:     START → excel_to_nl → compile → END   # --from-excel
compile 图:      START → parse_to_yaml → gate_review → END  # 单条 NL→YAML（LLM）
```

Discover / Run **不在** LangGraph 内（需浏览器与账号会话）。

---

## YAML 约定（简要）

- 元素用语义名，**不写 CSS/XPath**
- 多表填分用带表前缀的名字（如 `AI清洗得分输入框`），避免笼统 `得分输入框`
- 校验失败用 `表单校验提示`；成功用 `保存成功`；**禁止断言 `页面`**

```yaml
case_id: TC-QXGZ-015
steps:
  - action: open
    url: https://lead.z-niu.com/rule/clean/
  - action: click
    element: 清洗评分规则
  - action: click
    element: 修改
  - action: fill
    element: AI清洗得分输入框
    value: ""
  - action: click
    element: 保存
  - action: assert_visible
    element: 表单校验提示
```

---

## 常见问题

| 现象 | 处理 |
|------|------|
| `excel-to-nl` 报缺列 | 表头需含用例ID/标题/步骤/预期；见用例编写标准 |
| `compile` Key 为空 | `.env` 配置 API Key；`llm.yaml` 中 `backend: llm` |
| `element not in POM` | `discover --force`；勿手写 POM 冒充 |
| Excel 未回填 | `excel_backfill.enabled: true`；源表在 `excel/` |
| 飞书发不出 HTML | 正常：用 `REPORT_BASE_URL` 链接；Excel 可上传 |
| AI 外呼 / 造数被跳过 | 设计如此，结果为 Block |

---

## 端到端最短命令链

```bash
pip install -r requirements.txt && playwright install chromium

python main.py init --req MG0557
# 放入 excel/cases.xlsx，编辑 excel_nl.yaml
python main.py compile --req MG0557 --from-excel --llm deepseek
python main.py discover --req MG0557 --force --llm deepseek
python main.py run --req MG0557
```

打开 `allure-report.html` 与回填 Excel；部署与飞书详见 [`部署方案.md`](部署方案.md)。
