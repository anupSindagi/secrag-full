# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY ingester.py .
COPY sec_filing_parser.py .

# Ensure stdout/stderr are flushed
ENV PYTHONUNBUFFERED=1

# Run the ingester (loops daily)
CMD ["python", "ingester.py"]

