from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
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
        MockApiGateway.objects.get.assert_called_with(pk=123)
        MockApiGateway.objects.get.return_value.create_custom_domain.assert_called_with()

    @patch(
        "django_aws_api_gateway_websockets.management.commands.createCustomDomain.ApiGateway"
    )
    def test_a_gateway_with_nothing_left_to_do_is_refused(self, MockApiGateway):
        MockApiGateway.objects.get.return_value.needs_custom_domain = False

        with self.assertRaises(CommandError):
            self.call_command("--pk=123")

        MockApiGateway.objects.get.return_value.create_custom_domain.assert_not_called()

    @patch(
        "django_aws_api_gateway_websockets.management.commands.createCustomDomain.ApiGateway"
    )
    def test_a_domain_without_its_mapping_is_resumed(self, MockApiGateway):
        MockApiGateway.objects.get.return_value.needs_custom_domain = True

        self.call_command("--pk=123")

        MockApiGateway.objects.get.return_value.create_custom_domain.assert_called_once_with()
