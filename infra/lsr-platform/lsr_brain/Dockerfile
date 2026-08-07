FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Thư viện logic của platform (rating_agent.brain)
COPY src /app/src
COPY runner.py .
ENV PYTHONPATH=/app/src
CMD ["python", "runner.py"]
