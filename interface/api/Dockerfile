# Image de l'API KYST. Contexte de build : interface/api
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Le dossier est le package Python `api` : il est importé depuis son parent (/srv)
WORKDIR /srv/api

# Dépendances d'abord, pour garder ce calque en cache tant que uv.lock ne change pas
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --system --no-create-home kyst
USER kyst

ENV PATH="/srv/api/.venv/bin:$PATH"
EXPOSE 8000

# Un seul worker : l'état de coordination du planning vit dans ce processus
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
