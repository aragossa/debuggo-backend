# 1. Use an official Python runtime as the base image
FROM python:3.9-slim

# 2. Set environment variables
# Prevents Python from writing .pyc files and buffers stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Set the working directory in the container
WORKDIR /app

# 4. Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    gnupg \
    wget \
    curl \
    build-essential \
    chromium \
    chromium-driver \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    xvfb \
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