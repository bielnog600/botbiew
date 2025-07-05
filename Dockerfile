# Usa uma imagem base oficial do Python que contém os pacotes de desenvolvimento.
FROM python:3.10-bullseye

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# ETAPA 1: Instala as ferramentas de compilação e a biblioteca TA-Lib
# Esta abordagem é a mais confiável pois instala o pacote pré-compilado do Debian.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libta-lib-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ETAPA 2: Copia o arquivo de dependências
COPY requirements.txt .

# ETAPA 3: Instala as dependências Python.
# O pip agora encontrará a TA-Lib pré-instalada no sistema e o compilador gcc.
RUN pip install --no-cache-dir -r requirements.txt

# ETAPA 4: Copia o resto do código da sua aplicação.
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
