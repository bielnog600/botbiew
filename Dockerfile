git add Dockerfile requirements.txt
git commit -m "Fix Dockerfile with multi-stage build"
git push
5.  Vá ao **Coolify** e clique no botão **Deploy** (ou Redeploy).

# ----------------------------------------
# FASE 1: Build - Usa a imagem completa para garantir as ferramentas de compilação
# ----------------------------------------
FROM python:3.10 AS builder

# Define o diretório de trabalho.
WORKDIR /app

# Instala apenas o Tini, pois as ferramentas de build já estão incluídas.
RUN apt-get update -y && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de dependências.
COPY requirements.txt .

# Instala as dependências Python.
# Esta etapa agora funcionará, pois o ambiente tem todas as ferramentas necessárias.
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------
# FASE 2: Final - Usa a imagem 'slim' para um resultado leve
# ----------------------------------------
FROM python:3.10-slim-bookworm

WORKDIR /app

# Copia as bibliotecas Python instaladas da fase de build.
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# Copia o Tini da fase de build.
COPY --from=builder /usr/bin/tini /usr/bin/tini

# Copia todo o código do projeto.
COPY . .

# Define o entrypoint para usar o Tini.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Comando para executar a aplicação.
CMD ["python", "main.py"]

