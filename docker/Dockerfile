FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r backend/requirements.txt
RUN python3 scripts/setup_demo_repos.py
WORKDIR /app/backend
EXPOSE 8000
CMD ["python3", "-m", "app.main"]
