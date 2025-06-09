from django.conf import settings

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_aws_api_gateway_websockets",
]

SECRET_KEY = "dummy-key-for-docs"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

settings.configure(
    INSTALLED_APPS=INSTALLED_APPS,
    SECRET_KEY=SECRET_KEY,
    DATABASES=DATABASES,
)

import django

django.setup()
