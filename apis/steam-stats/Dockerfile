FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn requests
COPY app.py .
EXPOSE 5055
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5055", "app:app"]
