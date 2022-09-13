from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class CreateCustomDomainTestCase(SimpleTestCase):
    """Test the management command used to invoke the create_gateway method"""

    def call_command(self, *args, **kwargs):
        """Wrapper to allow the management command to be run"""
        call_command(
            "createCustomDomain",
            *args,
            stdout=StringIO(),
            stderr=StringIO(),
            **kwargs,
        )

    @patch(
        "django_aws_api_gateway_websockets.management.commands.createCustomDomain.ApiGateway"
    )
    def test_add_argument(self, MockApiGateway):
        self.call_command("--pk=123")
        MockApiGateway.objects.get.assert_called_with(
            pk=123, api_created=True, custom_domain_created=False
        )
        MockApiGateway.objects.get.return_value.create_custom_domain.assert_called_with()
