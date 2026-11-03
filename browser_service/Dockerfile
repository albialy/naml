FROM python:3.12-bookworm
WORKDIR /worker
COPY browser_service/requirements.txt .
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN pip install --no-cache-dir -r requirements.txt && python -m playwright install --with-deps chromium && useradd -m browser && chmod -R a+rX /opt/browsers
COPY browser_service/service.py ./service.py
USER browser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn service:app --host 0.0.0.0 --port ${PORT:-8000}"]
