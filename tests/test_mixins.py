from unittest.mock import MagicMock, patch

from django.test import TestCase

from django_aws_api_gateway_websockets.mixins import (
    AddWebSocketRouteToContextMixin,
    AppChannelWebSocketMixin,
)
from django_aws_api_gateway_websockets.models import (
    ApiGateway,
    ApiGatewayAdditionalRoute,
)


class BaseContextMixin:
    def get_context_data(self, **kwargs):
        return kwargs


class RouteContextView(AddWebSocketRouteToContextMixin, BaseContextMixin):
    pass


class AppChannelContextView(AppChannelWebSocketMixin, BaseContextMixin):
    pass


class AddWebSocketRouteToContextMixinTestCase(TestCase):
    def test_get_context_data_adds_route_and_channel_name(self):
        api_gateway = ApiGateway.objects.create(
            api_name="Mixin Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example.com/",
        )
        route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=api_gateway,
            name="Mixin Route",
            route_key="default",
            integration_url="https://www.example.com/ws/default",
        )

        view = RouteContextView()
        view.channel_name = "test-channel"

        context = view.get_context_data(existing=True)

        self.assertTrue(context["existing"])
        self.assertEqual(route, context["api_gateway_route"])
        self.assertEqual("test-channel", context["channel_name"])

    def test_get_context_data_adds_none_when_route_does_not_exist(self):
        view = RouteContextView()
        view.websocket_route_key = "missing-route"
        view.channel_name = "missing-channel"

        context = view.get_context_data()

        self.assertIsNone(context["api_gateway_route"])
        self.assertEqual("missing-channel", context["channel_name"])


class AppChannelWebSocketMixinTestCase(TestCase):
    @patch("django_aws_api_gateway_websockets.mixins.resolve")
    def test_get_context_data_uses_resolved_app_package(self, mocked_resolve):
        mocked_resolve.return_value.func.__module__ = (
            "django_aws_api_gateway_websockets.views"
        )

        api_gateway = ApiGateway.objects.create(
            api_name="App Channel Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example.com/",
        )
        route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=api_gateway,
            name="App Channel Route",
            route_key="django_aws_api_gateway_websockets",
            integration_url="https://www.example.com/ws/app",
        )

        view = AppChannelContextView()
        view.request = MagicMock(path_info="/example/")

        context = view.get_context_data(existing=True)

        self.assertTrue(context["existing"])
        self.assertEqual(route, context["api_gateway_route"])
        self.assertEqual(
            "django_aws_api_gateway_websockets",
            context["channel_name"],
        )
        self.assertEqual(
            "django_aws_api_gateway_websockets",
            view.websocket_route_key,
        )

    @patch("django_aws_api_gateway_websockets.mixins.resolve")
    def test_get_context_data_uses_app_channel_override_for_channel_only(
        self,
        mocked_resolve,
    ):
        mocked_resolve.return_value.func.__module__ = (
            "django_aws_api_gateway_websockets.views"
        )

        api_gateway = ApiGateway.objects.create(
            api_name="Override Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example.com/",
        )
        route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=api_gateway,
            name="Override Route",
            route_key="django_aws_api_gateway_websockets",
            integration_url="https://www.example.com/ws/app",
        )

        view = AppChannelContextView()
        view.request = MagicMock(path_info="/example/")
        view.app_channel_override = "override-channel"

        context = view.get_context_data()

        self.assertEqual(route, context["api_gateway_route"])
        self.assertEqual("override-channel", context["channel_name"])
        self.assertEqual(
            "django_aws_api_gateway_websockets",
            view.websocket_route_key,
        )
