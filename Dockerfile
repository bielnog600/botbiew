# Usa uma imagem base oficial do Python.
# Usamos a versão completa para garantir que todas as ferramentas estejam disponíveis.
FROM python:3.10-bullseye

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# Copia o arquivo de dependências primeiro.
COPY requirements.txt .

# ===================================================================
# Executa a instalação do sistema, compilação da TA-Lib e instalação
# das dependências Python em um ÚNICO passo para garantir a consistência.
# ===================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    # Baixa e compila a TA-Lib
    && wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -q -O - | tar -xzf - \
    && cd ta-lib/ \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib/ ta-lib-0.4.0-src.tar.gz \
    # ATUALIZA O CACHE DE BIBLIOTECAS DO SISTEMA (CRUCIAL)
    && ldconfig \
    # Agora, com a TA-Lib instalada E o cache atualizado, instala os pacotes Python
    && pip install --no-cache-dir -r requirements.txt \
    # Finalmente, remove as ferramentas de compilação para manter a imagem pequena
    && apt-get purge -y --auto-remove build-essential wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
