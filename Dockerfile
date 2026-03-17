# syntax=docker/dockerfile:1

FROM public.ecr.aws/docker/library/python:3.13-slim-bullseye
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 2080
CMD ["python", "app.py"]