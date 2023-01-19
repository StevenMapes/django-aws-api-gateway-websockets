from unittest.mock import MagicMock, patch

from botocore import exceptions
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase

from django_aws_api_gateway_websockets import admin, models


class CreateApiGatewaySimpleTestCase(SimpleTestCase):
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_empty_queryset(self, mocked_messages):
        """Empty queryset means nothing should run"""
        queryset = []

        admin.create_api_gateway(None, None, queryset)

        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_not_yet_created(self, mocked_messages):
        """When the record does not yet have an API that has been created, it should call create_gateway"""
        request = MagicMock()
        instance = MagicMock(
            api_created=False,
            custom_domain_created=False,
            api_name="Test API",
        )
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        instance.create_gateway.assert_called_with()
        mocked_messages.success.assert_called_with(
            request, f"API Gateway endpoint created for {instance.api_name}"
        )
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_already_created(self, mocked_messages):
        """When the api_created boolean is True the record should be skipped"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            api_name="Test API",
        )
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        self.assertEqual(0, instance.create_gateway.call_count)
        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_client_error_raised(self, mocked_messages):
        """When a ClientError occurs an error message should be added"""
        request = MagicMock()
        instance = MagicMock(
            api_created=False,
            custom_domain_created=False,
            api_name="Test API",
        )
        instance.create_gateway.side_effect = exceptions.ClientError(
            {"Error": {"Code": "A123", "Message": "Some error"}}, "apigateway"
        )
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        instance.create_gateway.assert_called_with()
        self.assertEqual(0, mocked_messages.success.call_count)
        mocked_messages.error.assert_called_with(
            request,
            (
                "An error occurred (A123) when calling the apigateway operation: Some error occurred when processing "
                f"{instance.api_name}"
            ),
        )


class CreatCustomDomainSimpleTestCase(SimpleTestCase):
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_empty_queryset(self, mocked_messages):
        """Empty queryset means nothing should run"""
        queryset = []

        admin.create_custom_domain(None, None, queryset)

        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_created_but_custom_domain_not_created(self, mocked_messages):
        """When the record does not yet have an API that has been created, it should call create_gateway"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            api_name="Test API",
            api_gateway_domain_name="ws.example.com",
        )
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        instance.create_custom_domain.assert_called_with()
        mocked_messages.success.assert_called_with(
            request,
            f"Custom Domain setup for {instance.api_name}. Next update DNS to point to {instance.api_gateway_domain_name}",
        )
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_and_custom_domain_both_created(self, mocked_messages):
        """When the api_created boolean is True the record should be skipped"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=True,
            api_name="Test API",
            api_gateway_domain_name="ws.example.com",
        )
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        self.assertEqual(0, instance.create_custom_domain.call_count)
        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_client_error_raised(self, mocked_messages):
        """When a ClientError occurs an error message should be added"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            api_name="Test API",
            api_gateway_domain_name="ws.example.com",
        )
        instance.create_custom_domain.side_effect = exceptions.ClientError(
            {"Error": {"Code": "A123", "Message": "Some error"}}, "apigateway"
        )
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        instance.create_custom_domain.assert_called_with()
        self.assertEqual(0, mocked_messages.success.call_count)
        mocked_messages.error.assert_called_with(
            request,
            (
                "An error occurred (A123) when calling the apigateway operation: Some error occurred when processing "
                f"{instance.api_name}"
            ),
        )


class AdminTestCase(TestCase):
    """Tests that require the database"""

    def setUp(self) -> None:
        self.user, _ = User.objects.get_or_create(
            username="test", is_staff=True, is_superuser=True
        )

    def test_WebSocketSessionAdmin_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.WebSocketSessionAdmin(
            model=models.WebSocketSession, admin_site=AdminSite()
        )
        request = RequestFactory().get("/view-path")
        site.get_queryset(request)

    def test_ApiGatewayAdmin_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.ApiGatewayAdmin(model=models.ApiGateway, admin_site=AdminSite())
        request = RequestFactory().get("/view-path")
        site.get_queryset(request)

    def test_ApiGatewayAdditionalRouteAdmin_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.ApiGatewayAdditionalRouteAdmin(
            model=models.ApiGatewayAdditionalRoute, admin_site=AdminSite()
        )
        request = RequestFactory().get("/view-path")
        site.get_queryset(request)

    def test_ApiGatewayAdditionalRouteInline_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.ApiGatewayAdditionalRouteInline(
            parent_model=models.ApiGatewayAdditionalRoute, admin_site=AdminSite()
        )
        request = RequestFactory().get("/view-path")
        request.user = self.user
        request.session = {}
        site.get_queryset(request)
