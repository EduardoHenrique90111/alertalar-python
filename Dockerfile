# =====================================================================
#  AlertaLar (Python) - imagem para publicação (Render, Google Cloud Run, VPS...)
#  No Google Cloud Run, use o arquivo implantar-cloud-run.sh.
#  A imagem leva só o pacote alertalar (com as migrações e a base oficial) e o front-end.
# =====================================================================
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# Dependências primeiro (acelera builds seguintes quando só o código muda)
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alertalar alertalar
COPY frontend frontend
RUN python -m compileall -q alertalar \
    && useradd --system --uid 10001 alertalar
USER alertalar

# A porta vem da variável PORT definida pelo provedor (padrão 8080)
EXPOSE 8080
CMD ["python", "-m", "alertalar"]
