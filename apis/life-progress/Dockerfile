FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY app.py .
EXPOSE 5051
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5051", "app:app"]
