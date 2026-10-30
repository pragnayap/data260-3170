# HW8 - image shared by the worker and the FastAPI wrapper (compose picks the command).
FROM python:3.12-slim
WORKDIR /app/code/hw08
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir confluent-kafka==2.16.1 fastapi==0.109.0 "uvicorn[standard]==0.27.0" pydantic==2.12.5
COPY code/hw08/ /app/code/hw08/
CMD ["python", "worker.py"]
