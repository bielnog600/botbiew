# Use Python 3.12 as required by the new pandas-ta version
FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies
# We include git because pandas-ta or other libs might need it
# We include build-essential for compiling libraries if wheels aren't found
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# Added --upgrade pip to ensure we have the latest wheel building capabilities
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Command to run the bot
CMD ["python", "main.py"]
