# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# Instala a biblioteca TA-Lib e suas ferramentas de desenvolvimento
# a partir dos repositórios oficiais do Debian. É muito mais simples e confiável.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libta-lib-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de dependências
COPY requirements.txt .

# Instala as dependências Python. O pip agora encontrará a TA-Lib pré-instalada no sistema.
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código da sua aplicação
COPY . .

# Comando para executar o bot quando o container iniciar
CMD ["python", "main.py"]
