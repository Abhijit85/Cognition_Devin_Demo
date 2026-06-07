PYTHON ?= python3.13

.PHONY: help venv install api streamlit up down logs test demo scan dashboard bootstrap clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv:  ## Create the local virtual environment
	$(PYTHON) -m venv .venv

install: venv  ## Install Python deps into .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

api:  ## Run the FastAPI orchestrator locally through .venv
	set -a; . .env; set +a; .venv/bin/uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000

streamlit:  ## Run the Streamlit dashboard locally through .venv
	set -a; . .env; set +a; .venv/bin/streamlit run dashboard/app.py --server.port 8501

up:  ## Bring up orchestrator + dashboard (uses .env)
	docker compose up --build -d

up-mock:  ## Bring up in mock mode (no Devin credentials needed)
	DEVIN_MOCK=1 docker compose up --build -d

down:  ## Stop everything
	docker compose down

logs:  ## Tail orchestrator logs
	docker compose logs -f orchestrator

test:  ## Run smoke tests in mock mode
	DEVIN_MOCK=1 DEVIN_ORG_ID=test .venv/bin/pytest tests/ -v

scan:  ## Manually trigger a scan via the running orchestrator
	curl -X POST http://localhost:8000/scan/run

demo:  ## Trigger scan + watch sessions stream (60s)
	set -a; . .env; set +a; .venv/bin/python scripts/demo_seed.py --watch

bootstrap:  ## Register the CVE Remediation Playbook with Devin (one-shot)
	set -a; . .env; set +a; .venv/bin/python scripts/bootstrap_playbook.py

dashboard:  ## Open the dashboard in your browser
	@command -v open >/dev/null && open http://localhost:8501 || \
	 command -v xdg-open >/dev/null && xdg-open http://localhost:8501 || \
	 echo "Open http://localhost:8501 manually"

clean:  ## Remove containers, volumes, and local state
	docker compose down -v
	rm -rf __pycache__ */__pycache__ */*/__pycache__ .pytest_cache
