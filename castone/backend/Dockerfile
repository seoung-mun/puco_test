FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security (optional but recommended)
RUN useradd -m appuser
USER appuser

EXPOSE 8000
