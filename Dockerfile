# ETAPA 1: Usar uma imagem base do Python mais completa que a 'slim'.
# 'bullseye' é a versão estável do Debian na qual o python:3.10 se baseia.
# Isso garante que os pacotes de desenvolvimento como 'libta-lib-dev' estejam disponíveis.
FROM python:3.10-bullseye

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# ETAPA 2: Instala a biblioteca TA-Lib e suas ferramentas de desenvolvimento
# a partir dos repositórios oficiais do Debian.
# Esta abordagem é mais simples e confiável do que a compilação manual.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libta-lib-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ETAPA 3: Copia o arquivo de dependências
COPY requirements.txt .

# ETAPA 4: Instala as dependências Python.
# O pip agora encontrará a TA-Lib pré-instalada no sistema.
RUN pip install --no-cache-dir -r requirements.txt

# ETAPA 5: Copia o resto do código da sua aplicação.
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
