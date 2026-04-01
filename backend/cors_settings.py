# Add this code to your settings.py or create a separate file and import it

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True  # In production, set this to False and use CORS_ALLOWED_ORIGINS
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite default port
    "http://127.0.0.1:5173",
]

CORS_ALLOWED_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
    'OPTIONS',
]

CORS_ALLOWED_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Make sure 'corsheaders' is in your INSTALLED_APPS
INSTALLED_APPS = [
    # ...existing apps...
    'corsheaders',
    # ...other apps...
]

# Make sure the CORS middleware is included and in the right order
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # This should be as high as possible
    'django.middleware.common.CommonMiddleware',
    # ...other middleware...
]
