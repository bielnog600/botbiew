# ===================================================================
# ETAPA 1: O Ambiente de Construção (Builder)
# Usamos uma imagem completa para garantir que todas as ferramentas de compilação estejam disponíveis.
# ===================================================================
FROM python:3.10-bullseye AS builder

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

# Cria um ambiente virtual para instalar as dependências Python
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia e instala os pacotes Python do requirements.txt
# O pip vai usar a TA-Lib que acabámos de compilar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


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
COPY --from=builder /opt/venv /opt/venv

# Copia o resto do código da sua aplicação
COPY . .

# Ativa o ambiente virtual para os comandos seguintes
ENV PATH="/opt/venv/bin:$PATH"

# Atualiza o cache de bibliotecas na imagem final
RUN ldconfig

# Comando para executar o bot quando o container iniciar
CMD ["python", "main.py"]
