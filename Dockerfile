# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# 1. Instala as dependências do sistema necessárias para compilar
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget

# 2. Baixa, compila e instala a biblioteca C da TA-Lib
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -q -O - | tar -xzf - \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib/ ta-lib-0.4.0-src.tar.gz \
    # 3. ATUALIZA O CACHE DE BIBLIOTECAS DO SISTEMA (CRUCIAL)
    && ldconfig

# 4. Copia e instala as dependências Python.
# O pip agora encontrará a TA-Lib e as ferramentas de compilação.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia o resto do código da sua aplicação.
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
