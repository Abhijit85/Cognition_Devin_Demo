FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (curl for healthchecks, git so pip-audit can resolve some sources)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY orchestrator ./orchestrator
COPY dashboard ./dashboard
COPY playbooks ./playbooks

# State volume
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000 8501

# Default: orchestrator API. Override in docker-compose for the dashboard.
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
