FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY conecta_agent ./conecta_agent
COPY app.py .
RUN useradd -m -u 1000 agent
USER agent
EXPOSE 8080
CMD ["opentelemetry-instrument", "python", "app.py"]
