# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# ===================================================================
# NOVO: Instala as dependências do sistema para a biblioteca TA-Lib
# Este passo é necessário para que o 'pip install TA-Lib' funcione.
# ===================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    && wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -q -O - | tar -xzf - \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib/ ta-lib-0.4.0-src.tar.gz \
    && apt-get remove -y build-essential wget \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# ===================================================================

# Copia o arquivo de dependências para o diretório de trabalho.
COPY requirements.txt .

# Instala as dependências do Python.
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
