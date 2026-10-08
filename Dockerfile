FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY wsgi.py .
ENV DATA_DIR=/data COOKIE_SECURE=1
VOLUME /data
EXPOSE 8000
# 1 worker + thread: SQLite resta semplice e sicuro, basta per un torneo.
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:8000", "wsgi:app"]
