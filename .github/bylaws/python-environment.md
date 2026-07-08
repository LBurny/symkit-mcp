# Python 环境管理子法

> 依据宪法第 7.2 条「环境即代码」订定

---

## 第 1 条：套件管理器优先级

```
uv > pip-tools > pip
```

### 1.1 uv 优先原则
1. **新项目必须使用 uv** 作为套件管理器
2. uv 速度比 pip 快 10-100 倍
3. 原生支持 lockfile 和虚拟环境

### 1.2 降级条件
仅在以下情况可使用 pip：
- 旧项目迁移成本过高
- CI 环境不支持 uv
- 特殊依赖冲突

---

## 第 2 条：虚拟环境规范

### 2.1 必须使用虚拟环境
```bash
# ✅ 正确
uv venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# ❌ 禁止全域安装
pip install package  # 在系统 Python 中
```

### 2.2 虚拟环境位置
```
project/
├── .venv/           # 虚拟环境（gitignore）
├── pyproject.toml   # 项目配置
└── uv.lock          # 依赖锁定（版控）
```

### 2.3 Python 版本
- 本项目使用 Python 3.12+
- 版本在 `pyproject.toml` 中明确指定

---

## 第 3 条：依赖管理

### 3.1 文件结构
```
pyproject.toml       # 主要依赖定义（必须）
uv.lock              # 依赖锁定档（必须，纳入版控）
requirements.txt     # 兼容性导出（可选，CI 用）
```

### 3.2 pyproject.toml 范本
```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.0",
    "sqlalchemy>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=7.4.0",
    "ruff>=0.1.0",
]
```

### 3.3 常用 uv 指令
```bash
# 初始化项目
uv init my-project
cd my-project

# 创建虚拟环境
uv venv

# 安装依赖
uv pip install -e ".[dev]"
uv sync  # 根据 uv.lock 同步

# 添加依赖
uv add fastapi
uv add --dev pytest

# 移除依赖
uv remove package-name

# 更新依赖
uv lock --upgrade

# 导出 requirements.txt（兼容 CI）
uv pip compile pyproject.toml -o requirements.txt
```

---

## 第 4 条：项目初始化流程

### 4.1 新项目（使用 uv）
```bash
# 1. 创建项目
uv init my-project
cd my-project

# 2. 设置 Python 版本
uv python pin 3.12

# 3. 安装开发依赖
uv add --dev pytest ruff mypy

# 4. 创建目录结构
mkdir -p src/domain src/application src/infrastructure src/presentation
mkdir -p tests/unit tests/integration tests/e2e
touch src/__init__.py tests/__init__.py
```

### 4.2 现有项目迁移
```bash
# 1. 从 requirements.txt 迁移
uv pip compile requirements.txt -o requirements.lock
uv venv
uv pip sync requirements.lock

# 2. 创建 pyproject.toml
uv init --no-workspace

# 3. 迁移依赖
uv add $(cat requirements.txt | grep -v "^#" | tr '\n' ' ')

# 4. 锁定依赖
uv lock
```

---

## 第 5 条：CI/CD 集成

### 5.1 GitHub Actions 使用 uv
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
      
      - name: Set up Python
        run: uv python install 3.11
      
      - name: Install dependencies
        run: uv sync --all-extras
      
      - name: Run tests
        run: uv run pytest
```

### 5.2 Docker 使用 uv
```dockerfile
FROM python:3.11-slim

# 安装 uv（从官方映像拷贝）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./

# 安装依赖（不使用虚拟环境）
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .
CMD ["python", "-m", "src.main"]
```

### 5.3 uvx 工具运行（类似 npx）
```bash
# 临时运行工具（不安装）
uvx ruff check .
uvx black --check .
uvx mypy src/

# 运行特定版本
uvx ruff@0.1.0 check .
```

---

## 第 6 条：常见问题

### Q1: uv 和 pip 可以混用吗？
A: 不建议。混用可能导致依赖冲突。若必须，先用 `uv pip` 取代 `pip`。

### Q2: 为什么不用 Poetry/Pipenv？
A: uv 比 Poetry 快 10-100 倍，且与 pip 完全兼容。Poetry 的 resolver 较慢。

### Q3: Windows 支持如何？
A: uv 完整支持 Windows。安装：`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

### Q4: 如何处理私有套件？
A: 在 `pyproject.toml` 中设置：
```toml
[tool.uv]
index-url = "https://pypi.org/simple"
extra-index-url = ["https://your-private-pypi.com/simple"]
```

---

## 附录：快速参考卡

| 操作 | uv 指令 | pip 对应 |
|------|---------|----------|
| 创建 venv | `uv venv` | `python -m venv .venv` |
| 安装套件 | `uv add package` | `pip install package` |
| 安装开发依赖 | `uv add --dev package` | `pip install package` |
| 安装全部 | `uv sync` | `pip install -r requirements.txt` |
| 更新 lock | `uv lock` | `pip-compile` |
| 运行命令 | `uv run pytest` | `pytest` |
| 查看依赖 | `uv pip list` | `pip list` |

---

*本子法版本：v1.0.0*
*依据：宪法第 7.2 条*
