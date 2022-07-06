#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "make_migrations_settings")
    from django.core.management import execute_from_command_line

    args = sys.argv + ["makemigrations", "django_aws_api_gateway_websockets"]
    execute_from_command_line(args)
