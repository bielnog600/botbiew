# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# ===================================================================
# ETAPA 1: Instala as dependências do sistema para a biblioteca TA-Lib
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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ===================================================================
# NOVO: Define a variável de ambiente para que o sistema encontre a TA-Lib
# ===================================================================
ENV LD_LIBRARY_PATH /usr/lib

# ===================================================================
# ETAPA 2: Instala as dependências do Python
# ===================================================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===================================================================
# ETAPA 3: Copia o código da sua aplicação
# ===================================================================
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
