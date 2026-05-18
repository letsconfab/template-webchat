FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libmagic1 \
    libreoffice \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/HKUDS/RAG-Anything.git /tmp/RAG-Anything

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN pip install --no-cache-dir "colorlog>=6.10.1"
RUN pip install --no-cache-dir -e "/tmp/RAG-Anything[image,text]"

COPY backend /app/backend
COPY rag_service /app/rag_service

ENV PYTHONPATH=/app
EXPOSE 8010

CMD ["uvicorn", "rag_service.app:app", "--host", "0.0.0.0", "--port", "8010"]
