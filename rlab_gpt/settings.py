from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG') == 'True'

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",  # 👈 REQUIRED by allauth

    # --- Local Apps (Moved UP to override allauth templates) ---
    "core",  

    # --- 3rd Party Apps (Allauth) ---
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google", # Google Provider
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    
    # 👈 REQUIRED: Allauth middleware (must be after AuthenticationMiddleware)
    "allauth.account.middleware.AccountMiddleware",
]

# Make sure this matches your actual project folder name!
ROOT_URLCONF = "rlab_gpt.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # 👈 CRITICAL FIX: Points to your templates folder
        "APP_DIRS": True,  
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request", # 👈 Required by allauth
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.user_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "rlab_gpt.wsgi.application"

# Database: default SQLite
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --- AUTHENTICATION BACKENDS ---
AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods (e-mail login)
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator" },
    { "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator" },
    { "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator" },
    { "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator" },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ================= STATIC & MEDIA FILES =================
# Static files (CSS, JS, Images)
STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "core" / "static",
]

# Media Files (Uploaded by Users) - ADDED THIS
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ================= EMAIL CONFIGURATION =================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')

# ================= ALLAUTH CONFIGURATION (UPDATED) =================
SITE_ID = 1

# 1. Login Logic: Use Email (Replaces ACCOUNT_AUTHENTICATION_METHOD)
ACCOUNT_LOGIN_METHODS = {'email'}

# 2. Signup Fields: Explicitly define required fields
# Replaces ACCOUNT_EMAIL_REQUIRED and ACCOUNT_USERNAME_REQUIRED
# The '*' denotes that the field is required.
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']

# 3. Auto-Generate Username from Email (Frictionless)
SOCIALACCOUNT_AUTO_SIGNUP = True   # <--- KEY FIX: Skips additional signup forms
ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'

# 4. Verification
ACCOUNT_EMAIL_VERIFICATION = 'none' # Google handles verification

# Redirects
LOGIN_URL = "/login/" 
LOGIN_REDIRECT_URL = "/"  # Redirect to home after login
LOGOUT_REDIRECT_URL = "/" # Redirect to home after logout

# Google Provider Settings
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    }
}