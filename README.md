# LangGraph-uitest

基于 **自然语言用例 / Excel → LLM 编译 YAML → POM Discover → Playwright 执行 → Allure + Excel 回填** 的 UI 自动化测试框架。

运行期不调用大模型：YAML + POM 在本地确定性执行。大模型只用于 **NL→YAML 编译** 与 **元素 Discover（可选）**。

---

## 能力概览

| 阶段 | 作用 |
|------|------|
| `init` | 创建需求工作区 `runs/<req>/` |
| Excel → NL | 将用例表整理为自然语言（可脚本生成） |
| `compile` | **必须走大模型**，NL → `yaml/<case_id>.yaml`（覆盖同名文件） |
| `discover` | 根据 YAML 元素名在页面上绑定 POM 定位器 |
| `run` | 执行 YAML，生成 Allure，回填 Excel；若开启 notify 则自动发报告 |
| `notify` | 仅发送已有 Excel/HTML 报告（不重跑） |
| `excel-backfill` | 仅根据已有 Allure 结果回填 Excel（不重跑） |

自动执行会跳过带以下标记的用例：`manual` / `ai_outbound` / `needs_fixture`（或 `meta.manual_only` / `meta.needs_fixture`）。

---

## 目录结构

```
LangGraph-uitest/
├── main.py                 # CLI 入口
├── requirements.txt
├── .env                    # API Key、账号等（勿提交）
├── config/
│   ├── settings.yaml       # 浏览器、登录、Excel 回填
│   ├── llm.yaml            # 大模型 profile（deepseek / zhipu / gpt）
│   └── accounts.yaml       # 测试账号引用
├── framework/              # 核心：schema / runner / compile / discover / POM
├── tests/                  # pytest（含 YAML runner）
└── runs/<req_id>/          # 每个需求一套产物
    ├── nl/                 # 自然语言用例 *.nl.md
    ├── yaml/               # 可执行用例 *.yaml（统一命名）
    ├── pom/elements.yaml   # 元素定位
    ├── excel/              # 原始用例表（建议 cases.xlsx）
    ├── allure-results/     # 原始 Allure 结果
    ├── allure-report.html  # 单文件报告（run 后生成）
    ├── logs/               # 执行日志
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

```bash
# 大模型（compile 必填其一，默认 deepseek）
DEEPSEEK_API_KEY=sk-...
# ZHIPUAI_API_KEY=...
# OPENAI_API_KEY=...

# 登录账号（与 config/accounts.yaml 中 account_ref 对应）
# 具体变量名以 accounts.yaml / bootstrap 配置为准
```

### 3. 常用配置

- `config/settings.yaml`
  - `browser.headless`：无头模式（`true`/`false`）
  - `browser.slow_mo_ms`：有界面时放慢操作便于观察
  - `excel_backfill.enabled`：run 后是否回填 Excel
- `config/llm.yaml`
  - `backend: llm`：正式编译必须走大模型
  - `active: deepseek`：默认 profile

---

## 标准执行流程（推荐）

以需求号 `MG0557` 为例。

### 步骤 1：初始化工作区

```bash
python main.py init --req MG0557
```

创建 `runs/MG0557/` 下 `nl/`、`yaml/`、`pom/`、`excel/`、`logs/` 等目录。

### 步骤 2：准备用例输入

1. 将 Excel 用例表放到：

   ```text
   runs/MG0557/excel/cases.xlsx
   ```

   （也可放 `Downloads/MG0557*.xlsx`，回填时会自动查找。）

2. 生成 / 编写 NL（自然语言），例如：

   ```bash
   python runs/MG0557/_regen_nl_from_excel.py
   ```

   NL 放在 `runs/MG0557/nl/*.nl.md`。

   约定标记（编译后会写入 skip 标签，自动跑时跳过）：

   - `【人工/AI外呼】` → `manual` + `ai_outbound`
   - `【需造数】` → `needs_fixture`

### 步骤 3：NL → YAML（大模型编译）

```bash
python main.py compile --req MG0557 --llm deepseek
```

说明：

- 输出统一为 `runs/MG0557/yaml/<case_id>.yaml`，**同名直接覆盖**
- 不再使用 `*.compiled.yaml` 双轨命名
- 正式编译禁止 stub；仅调试可加 `--allow-stub`
- 换模型：`--llm zhipu` 或 `--llm gpt`（需对应 Key）

### 步骤 4：Discover 绑定 POM

YAML 里是语义元素名（如 `清洗评分规则`、`得分输入框`），需落到真实定位器：

```bash
# 启发式 + 大模型补全未绑定元素（推荐）
python main.py discover --req MG0557 --force --llm deepseek

# 仅启发式，不调 LLM
python main.py discover --req MG0557 --force --no-llm
```

产物：`runs/MG0557/pom/elements.yaml`、`runs/MG0557/bindings/discover.yaml`。

> 若 run 报 `element not in POM: 'xxx'`，优先重新 discover 或手工补 POM。

### 步骤 5：执行用例

```bash
# 默认：无头执行 + Allure + Excel 回填
python main.py run --req MG0557

# 传给 pytest 的额外参数（注意 --）
python main.py run --req MG0557 -- -q --tb=line

# 指定回填用的源 Excel
python main.py run --req MG0557 --excel D:\path\to\cases.xlsx

# 本次不回填 Excel
python main.py run --req MG0557 --no-excel-backfill
```

有界面观察执行过程时，先改 `config/settings.yaml`：

```yaml
browser:
  headless: false
  slow_mo_ms: 400
```

### 步骤 6：查看结果

| 产物 | 位置 |
|------|------|
| Allure 报告 | `runs/MG0557/allure-report.html`（可双击打开） |
| Allure 原始结果 | `runs/MG0557/allure-results/` |
| Excel 回填 | `runs/MG0557/MG0557_结果回填.xlsx` |
| 执行日志 | `runs/MG0557/logs/` |

Excel「测试结果」取值：

- **通过**：自动执行 passed
- **失败**：自动执行 failed/broken（含截图）
- **Block**：人工/AI外呼、需造数、或本次未执行

### 步骤 7：测试报告自动通知（可选）

`run` 结束后可自动发送；也可单独补发：

```bash
python main.py notify --req MG0557
```

`.env` 填凭证与报告访问根地址，`config/notify.yaml` 打开开关：

```text
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_CHAT_ID=oc_xxx
REPORT_BASE_URL=https://uitest.example.com/reports
```

飞书消息会带 **报告链接**（不再上传超大 HTML）。服务器用 Nginx 把该前缀指到项目 `runs/`：

```nginx
location /reports/ {
    alias /opt/LangGraph-uitest/runs/;
    autoindex off;
}
```

本地可临时起静态服务验证：`python -m http.server 8080 --directory runs`，并设 `REPORT_BASE_URL=http://127.0.0.1:8080`。

仅用已有 Allure 重新回填（不重跑浏览器）：

```bash
python main.py excel-backfill --req MG0557
python main.py excel-backfill --req MG0557 --excel D:\path\to\cases.xlsx
```

---

## 命令速查

```bash
# 帮助
python main.py -h
python main.py run -h

# 初始化
python main.py init --req <REQ>

# 编译（LLM → yaml/*.yaml）
python main.py compile --req <REQ> --llm deepseek

# 发现元素 → POM
python main.py discover --req <REQ> [--force] [--llm deepseek | --no-llm]

# 执行
python main.py run --req <REQ> [--excel PATH] [--no-excel-backfill] [-- -q]

# 框架烟测（不跑业务用例）
python main.py run --req <REQ> --smoke

# 仅 Excel 回填
python main.py excel-backfill --req <REQ> [--excel PATH]
```

---

## YAML 用例约定（简要）

- `case_id` / `title` / `requirement_id` / `base_url`
- `preconditions`：如 `auth: logged_in` + `account_ref: default_tester`
- `steps`：白名单 action（`open` / `click` / `fill` / `assert_*` 等），元素用语义名，**不写 CSS/XPath**
- `tags` / `meta`：控制是否自动执行、编译来源等

示例（片段）：

```yaml
case_id: TC-QXGZ-005
requirement_id: MG0557
base_url: https://lead.z-niu.com
preconditions:
  - auth: logged_in
    account_ref: default_tester
steps:
  - action: open
    url: https://lead.z-niu.com/rule/clean/
  - action: click
    element: 清洗评分规则
  - action: click
    element: 修改
  - action: fill
    element: 得分输入框
    value: "-1"
```

---

## 常见问题

| 现象 | 处理 |
|------|------|
| `compile` 报 Key 为空 | 在 `.env` 配置对应 `*_API_KEY`；`llm.yaml` 中 `backend: llm` |
| `element not in POM` | 执行 `discover --force`，或手工编辑 `pom/elements.yaml` |
| Excel 未回填 | 确认 `excel_backfill.enabled: true`，源表在 `runs/<req>/excel/` 或 Downloads |
| 想看浏览器操作 | `headless: false`，可加大 `slow_mo_ms` |
| AI 外呼 / 造数用例被跳过 | 符合设计；结果在 Excel 中记为 **Block**，等人工执行 |

---

## 端到端最短命令链

```bash
pip install -r requirements.txt && playwright install chromium

python main.py init --req MG0557
# 放入 excel/cases.xlsx，并生成 nl/
python main.py compile --req MG0557 --llm deepseek
python main.py discover --req MG0557 --force --llm deepseek
python main.py run --req MG0557
```

打开 `runs/MG0557/allure-report.html` 与 `runs/MG0557/MG0557_结果回填.xlsx` 查看结果。
