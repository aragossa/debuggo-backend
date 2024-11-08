# 1. Use an official Python runtime as the base image
FROM python:3.9-slim

# 2. Set environment variables
# Prevents Python from writing .pyc files and buffers stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Set the working directory in the container
WORKDIR /app

# 4. Install system dependencies (if any)
# Example: If you need build tools or other system packages, add them here
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. Upgrade pip
RUN pip install --upgrade pip

# 6. Copy only the requirements file to leverage Docker layer caching
COPY requirements.txt .

# 7. Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copy the rest of the application code
COPY database.sql .
COPY fetch_test_steps.py .
COPY geminiAPI.py .
COPY image_testcases.py .
COPY image_validator.py .
COPY json_testcases.py .
COPY main.py .
COPY script_executor.py .
COPY test_case_builder.py .
COPY test_generate_code.py .
COPY test_selenium.py .
COPY clear_data.py .

# 9. Expose the port the app runs on
EXPOSE 8000

# 10. Define the default command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
