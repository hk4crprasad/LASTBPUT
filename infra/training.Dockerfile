FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv
WORKDIR /workspace/services/api
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-install-project
ENV PATH="/workspace/services/api/.venv/bin:$PATH" PYTHONPATH=/workspace/services/api OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OFFLINE_TRAINING=true
COPY services/api/app ./app
COPY scripts/offline_train.py /workspace/scripts/offline_train.py
CMD ["python", "-m", "app.cli", "train", "--data", "/workspace/research/starter/data", "--out", "/workspace/research/evaluation/new-training-version"]
