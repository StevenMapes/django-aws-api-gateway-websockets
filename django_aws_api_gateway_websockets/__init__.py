import django

if django.VERSION < (3, 2):
    default_app_config = "django_aws_api_gateway_websockets.apps.DjangoAwsApiGatewayWebsocketsConfig"