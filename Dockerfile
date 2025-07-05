# ===================================================================
# ETAPA 1: O Ambiente de Construção (Builder)
# Usamos uma imagem completa para garantir que todas as ferramentas de compilação estejam disponíveis.
# ===================================================================
FROM python:3.10-bullseye as builder

# Define o diretório de trabalho
WORKDIR /usr/src/app

# Instala as dependências do sistema necessárias para compilar a TA-Lib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget

# Baixa, compila e instala a biblioteca C da TA-Lib
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -q -O - | tar -xzf - \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install

# Instala as dependências Python em um local específico dentro do builder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target=/usr/src/app/packages


# ===================================================================
# ETAPA 2: A Imagem Final
# Esta é a imagem leve que será realmente executada.
# ===================================================================
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia a biblioteca TA-Lib já compilada do estágio de construção
COPY --from=builder /usr/lib/libta_lib.so.0 /usr/lib/
COPY --from=builder /usr/lib/libta_lib.so.0.0.0 /usr/lib/

# Copia os pacotes Python já instalados do estágio de construção
COPY --from=builder /usr/src/app/packages /usr/local/lib/python3.10/site-packages

# Copia o resto do código da sua aplicação
COPY . .

# Comando para executar o bot quando o container iniciar
CMD ["python", "main.py"]
