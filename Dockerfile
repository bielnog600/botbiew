# ===================================================================
# ETAPA 1: O Ambiente de Construção (Builder)
# Aqui instalamos todas as ferramentas pesadas e compilamos tudo.
# ===================================================================
FROM python:3.10-slim as builder

# Define o diretório de trabalho
WORKDIR /app

# Instala as dependências do sistema necessárias para compilar a TA-Lib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget

# Baixa, compila e instala a biblioteca C da TA-Lib
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -q -O - | tar -xzf - \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib/ ta-lib-0.4.0-src.tar.gz

# Cria um ambiente virtual para instalar as dependências Python
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia e instala os pacotes Python do requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ===================================================================
# ETAPA 2: A Imagem Final
# Esta é a imagem leve que será realmente executada.
# ===================================================================
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala APENAS a biblioteca de runtime da TA-Lib, que é muito mais leve
RUN apt-get update && apt-get install -y --no-install-recommends libta-lib0 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copia o ambiente virtual com os pacotes já instalados da etapa de construção
COPY --from=builder /opt/venv /opt/venv

# Copia o resto do código da sua aplicação
COPY . .

# Ativa o ambiente virtual para os comandos seguintes
ENV PATH="/opt/venv/bin:$PATH"

# Comando para executar o bot quando o container iniciar
CMD ["python", "main.py"]
