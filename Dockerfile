# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# ===================================================================
# ETAPA 1: Instala as dependências do sistema para a biblioteca TA-Lib
# Incluindo 'build-essential' que contém o compilador 'gcc'.
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
# ETAPA 2: Instala as dependências do Python
# Agora, o 'pip install TA-Lib' encontrará o 'gcc' e a biblioteca TA-Lib
# que foram instalados na etapa anterior.
# ===================================================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===================================================================
# ETAPA 3: Copia o código da sua aplicação
# ===================================================================
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
