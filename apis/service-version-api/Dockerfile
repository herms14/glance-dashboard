FROM python:3.11-slim

WORKDIR /app

# Install SSH client for remote Docker host access
RUN apt-get update && apt-get install -y openssh-client curl && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5070

CMD ["gunicorn", "-b", "0.0.0.0:5070", "--timeout", "120", "--workers", "2", "app:app"]
