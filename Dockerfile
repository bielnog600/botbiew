# ----------------------------------------
# FASE 1: Build
# ----------------------------------------
# Define a imagem base do Python. A versão 'slim' é mais leve.
FROM python:3.10-slim AS builder

# Define o diretório de trabalho dentro do contêiner.
WORKDIR /app

# Instala as dependências mínimas do sistema, incluindo as ferramentas de compilação
# e os cabeçalhos de desenvolvimento do Python para instalar pacotes.
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    tini \
    build-essential \
    python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Copia o arquivo de dependências para o contêiner.
COPY requirements.txt .

# Instala as dependências Python.
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------
# FASE 2: Final
# ----------------------------------------
# Define a imagem final, mais leve que a de build.
FROM python:3.10-slim

WORKDIR /app

# Copia as bibliotecas Python instaladas da fase de build.
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# Copia o Tini para ser o entrypoint.
COPY --from=builder /usr/bin/tini /usr/bin/tini

# Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# Define o entrypoint para usar o Tini, que gerencia processos zumbis.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Comando para executar a aplicação quando o contêiner iniciar.
CMD ["python", "main.py"]

