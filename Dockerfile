# Usa a mesma imagem base leve que você já estava usando
FROM python:3.10-slim-bookworm

# Define o diretório de trabalho
WORKDIR /app

# 1. Instala dependências do sistema operacional
# git: necessário caso alguma lib precise ser baixada do GitHub
# build-essential: necessário para compilar bibliotecas C/C++ (comum em data science)
# tini: gerenciador de processos para containers (evita zumbis)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# 2. Atualiza o pip para a versão mais recente (ajuda a resolver problemas de 'no matching distribution')
RUN pip install --upgrade pip

# 3. Copia e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copia o restante do código
COPY . .

# 5. Configura o ponto de entrada usando Tini
ENTRYPOINT ["/usr/bin/tini", "--"]

# 6. Comando para iniciar o bot
CMD ["python", "main.py"]
