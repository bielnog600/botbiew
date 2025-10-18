# ----------------------------------------
# FASE 1: Build
# ----------------------------------------
# Define a imagem base do Python, especificando a versão estável do Debian (Bookworm).
FROM python:3.10-slim-bookworm AS builder

# Define o diretório de trabalho dentro do contêiner.
WORKDIR /app

# Instala as dependências do sistema, incluindo as ferramentas de compilação
# e os cabeçalhos de desenvolvimento para a versão exata do Python (3.10).
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    tini \
    build-essential \
    python3.10-dev && \
    rm -rf /var/lib/apt/lists/*

# Copia o arquivo de dependências para o contêiner.
COPY requirements.txt .

# Instala as dependências Python.
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------
# FASE 2: Final
# ----------------------------------------
# Define a imagem final, baseada na mesma versão estável.
FROM python:3.10-slim-bookworm

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

