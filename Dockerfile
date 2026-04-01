FROM python:3.11-slim

# Prevent python from writing pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for OpenCV, ML libraries, and Git 
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn python-dotenv

# Copy all the project files
COPY . .

# Expose port
EXPOSE 8000

# Run collectstatic if needed, and database migrations before starting the server
CMD gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120120