FROM python:3.10-slim

WORKDIR /app

# Instala dependências do sistema necessárias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        wget \
        curl \
        gcc \
        make \
        libffi-dev \
        libssl-dev \
        && rm -rf /var/lib/apt/lists/*

# Baixa e compila TA-Lib manualmente
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzvf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    ./configure --prefix=/usr && \
    make && make install && \
    cd .. && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Agora o pip encontra a lib ta-lib instalada!
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "app.main"]
