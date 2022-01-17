from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DjangoAwsApiGatewayWebsocketsConfig(AppConfig):
    name = "django_aws_api_gateway_websockets"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = _("Django AWS ApiGateway Websockets")
