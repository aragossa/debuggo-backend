# 1. Use an official Python runtime as the base image
FROM python:3.9-slim

# 2. Set environment variables
# Prevents Python from writing .pyc files and buffers stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Set the working directory in the container
WORKDIR /app

# 4. Install system dependencies and Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    gnupg2 \
    libgconf-2-4 \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 5. Create directory for ChromeDriver
RUN mkdir -p /root/.cache/selenium/chromedriver/linux64 \
    && chmod -R 777 /root/.cache/selenium

# 6. Upgrade pip
RUN pip install --upgrade pip

# 7. Copy only the requirements file to leverage Docker layer caching
COPY requirements.txt .

# 8. Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 9. Copy the rest of the application code
COPY . .

# 10. Expose the port the app runs on
EXPOSE 8000

# 11. Define the default command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
