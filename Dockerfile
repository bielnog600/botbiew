# Usa a imagem base leve do Python
FROM python:3.10-slim-bookworm

# Define o diretório de trabalho
WORKDIR /app

# 1. Instala dependências do sistema
# Mantemos git/build-essential, curl e tini
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# 2. Atualiza o pip para evitar erros antigos
RUN pip install --upgrade pip

# 3. Copia o arquivo de dependências
COPY requirements.txt .

# 4. Instala as dependências
# A flag '--pre' é OBRIGATÓRIA para o pandas-ta funcionar via PyPI
RUN pip install --no-cache-dir --pre -r requirements.txt

# 5. Copia o código do bot
COPY . .

# 6. Configura o inicializador de processos
ENTRYPOINT ["/usr/bin/tini", "--"]

# 7. Comando para iniciar o bot
CMD ["python", "main.py"]
