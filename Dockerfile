FROM python:3.10-slim-bookworm

WORKDIR /app

# Instala dependências do sistema (git, curl, etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Atualiza o pip
RUN pip install --upgrade pip

# Copia e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY . .

# Comando de entrada
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]
