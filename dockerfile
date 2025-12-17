# Use Python 3.12 slim as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy all files from the current directory to /app
COPY . /app

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose any necessary ports (if needed, e.g., for debugging; bot doesn't need ports)
# EXPOSE 8080  # Optional, Telegram bot uses polling, no ports required

# Command to run the bot
CMD ["python", "run.py"]