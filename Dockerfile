# Security Analyzer console. Python standard library plus jsonschema.
# Build:  docker build -t security-analyzer .
# Run:    docker run --rm -p 8765:8765 -e CONSOLE_TOKEN=choose-a-long-random-value -e CONSOLE_ALLOWED_HOSTS=your.host.name security-analyzer
# Then open  http://localhost:8765/?token=choose-a-long-random-value
# READ docs/DEPLOY.md first: the console runs the tests of every project uploaded to it.
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . /app
USER app
ENV PORT=8765 PYTHONUNBUFFERED=1
EXPOSE 8765
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/healthz')"
CMD ["python", "ui/server.py", "--host", "0.0.0.0"]
