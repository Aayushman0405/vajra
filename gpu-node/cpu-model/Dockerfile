FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi==0.110.0 \
    uvicorn[standard]==0.29.0 \
    transformers==4.39.3 \
    torch==2.1.2 \
    accelerate==0.28.0 \
    sentencepiece==0.1.99 \
    protobuf==4.25.3 \
    numpy==1.26.4 \
    huggingface-hub==0.22.2

# Copy the CPU model code
COPY cpu_model_server.py .

EXPOSE 8000

CMD ["uvicorn", "cpu_model_server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
