FROM python:3.13-slim
WORKDIR /app
COPY backend/ ./backend/
COPY index.html ./index.html
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 helpline
USER helpline
EXPOSE 8000
CMD ["python", "backend/server.py"]
