FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y openssh-client && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 9102
CMD ["gunicorn", "-b", "0.0.0.0:9102", "app:app"]
