.PHONY: help up up-light down stop install dev server test test-unit test-integration test-system test-cov e2e e2e-verbose lint format init-db init-knowledge clean clean-py status

PORT := 8000
HOST := 0.0.0.0

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── Docker Services ────────────────────────────────────────────────

up: ## 启动全部依赖服务 (Langfuse + Postgres + ChromaDB + Redis)
	docker compose up -d
	@echo "\n\033[32m✅ 全部服务已启动\033[0m"
	@echo "  Langfuse:   http://localhost:3000"
	@echo "  ChromaDB:   http://localhost:8001"
	@echo "  Redis:      localhost:6379"
	@echo "  Postgres:   localhost:5432"

up-light: ## 轻量启动 (仅 ChromaDB)
	docker compose up -d chromadb
	@echo "\n\033[32m✅ 轻量模式启动\033[0m"
	@echo "  ChromaDB:   http://localhost:8001"
	@echo "  提示: 使用 SQLite 作为存储层，无需 Postgres/Redis"

down: ## 停止全部 Docker 服务
	docker compose down

stop: ## 一键关闭全部服务 (Docker + dev server)
	@echo "Stopping dev server..."
	@pkill -f "uvicorn langops.web" 2>/dev/null || true
	@pkill -f "python -m langops.server" 2>/dev/null || true
	@echo "Stopping Docker services..."
	@docker compose down 2>/dev/null || true
	@echo "\033[32m✅ 全部服务已停止\033[0m"

# ─── Python Environment ─────────────────────────────────────────────

install: ## 创建 venv 并安装全部依赖（含 dev）
	uv sync --dev
	@echo "\033[32m✅ 依赖安装完成\033[0m"

# ─── Server ─────────────────────────────────────────────────────────

dev: ## 启动开发服务器 (热重载, debug 模式)
	DEBUG=true uv run python -m langops.server

server: ## 启动生产服务器
	uv run python -m langops.server

# ─── Database ───────────────────────────────────────────────────────

init-db: ## 初始化数据库 (创建 SQLite 表结构)
	@mkdir -p .langops
	uv run python -c "from langops.storage import SqlStorage; import asyncio; asyncio.run(SqlStorage('sqlite:///.langops/data.db').initialize()); print('\033[32m✅ 数据库初始化完成\033[0m -> .langops/data.db')"

init-knowledge: ## 初始化知识库 (写入故障案例到 ChromaDB)
	uv run python scripts/init_knowledge.py

# ─── Testing ────────────────────────────────────────────────────────

test: clean-py ## 运行全部测试
	uv run pytest tests/ -v

test-unit: clean-py ## 运行单元测试
	uv run pytest tests/unit/ -v

test-integration: clean-py ## 运行集成测试
	uv run pytest tests/integration/ -v

test-webhooks: clean-py ## 运行 Webhook 回调集成测试 (AlertManager + 阿里云CMS)
	uv run pytest tests/integration/test_webhook_alertmanager.py tests/integration/test_webhook_aliyun_cms.py -v --tb=short

test-webhooks-verbose: clean-py ## 运行 Webhook 回调集成测试 (详细输出)
	uv run pytest tests/integration/test_webhook_alertmanager.py tests/integration/test_webhook_aliyun_cms.py -v -s --tb=long

test-system: clean-py ## 运行系统集成测试 (输入校验 + 端到端 + 采集器 + 降噪)
	uv run pytest tests/system/ -v --tb=short

test-system-verbose: clean-py ## 运行系统集成测试 (详细输出)
	uv run pytest tests/system/ -v -s --tb=long

test-cov: clean-py ## 运行测试并生成覆盖率报告
	uv run pytest tests/ -v --cov=langops --cov-report=term-missing

# ─── E2E (零 Docker，自动启动/停止 server) ─────────────────────────

e2e: clean-py ## E2E 端到端验证 (零 Docker，自动起停 server)
	@echo "\n\033[36m═══ E2E 端到端集成测试 ═══\033[0m"
	@echo "  模式: 本地文件 ChromaDB + SQLite (无需 Docker)"
	@echo "  端口: 18100 (自动启动/停止)\n"
	uv run pytest tests/e2e/ -v --tb=short

e2e-verbose: clean-py ## E2E 端到端验证 (详细输出)
	@echo "\n\033[36m═══ E2E 端到端集成测试 (verbose) ═══\033[0m"
	uv run pytest tests/e2e/ -v -s --tb=long

# ─── Code Quality ───────────────────────────────────────────────────

lint: ## 静态检查 (flake8 + mypy)
	uv run flake8 src/
	uv run mypy src/

format: ## 格式化代码 (black + isort)
	uv run black src/ tests/
	uv run isort src/ tests/

# ─── Utilities ──────────────────────────────────────────────────────

clean: ## 清理缓存和临时文件
	rm -rf .mypy_cache .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-py: ## 清理 Python 运行时产物 (__pycache__, .pyc, .egg-info)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

status: ## 查看 Docker 服务状态
	docker compose ps

logs: ## 查看 Docker 服务日志
	docker compose logs -f

# ─── Quick Start ────────────────────────────────────────────────────

setup: install init-db ## 一键安装并初始化 (首次使用)
	@echo "\n\033[32m✅ 环境准备就绪\033[0m"
	@echo "  运行 make dev 启动开发服务器"
	@echo "  运行 make up 启动全部依赖服务"

start: up init-knowledge server ## 一键启动全部服务 + API
	@echo "\n\033[32m✅ LangOps 已启动\033[0m"
	@echo "  API:    http://localhost:$(PORT)"
	@echo "  文档:  http://localhost:$(PORT)/docs"
	@echo "  Web UI: http://localhost:$(PORT)/ui"
