# Image de l'API KYST. Contexte de build : racine du depot.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Le dossier est le package Python `api` : il est importé depuis son parent (/srv)
WORKDIR /srv/api

# Dépendances d'abord, pour garder ce calque en cache tant que uv.lock ne change pas
COPY interface/api/pyproject.toml interface/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY interface/api/ ./
COPY optimiseur/ /srv/optimiseur/
COPY prediction/ /srv/prediction/

ENV PYTHONPATH=/srv

RUN useradd --system --no-create-home kyst
USER kyst

ENV PATH="/srv/api/.venv/bin:$PATH"
EXPOSE 8000

# Un seul worker : l'état de coordination du planning vit dans ce processus
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
