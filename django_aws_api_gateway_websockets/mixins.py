import sys

from django.urls import resolve

from django_aws_api_gateway_websockets.models import ApiGatewayAdditionalRoute


class AddWebSocketRouteToContextMixin:
    """Adds the APIGateway Route to the Content"""

    websocket_route_key = (
        "default"  # Ensure you override this if you are not using the default route
    )
    channel_name = ""

    def get_context_data(self, **kwargs) -> dict:
        """Adds the Websocket route connection to the context"""

        context = super().get_context_data(**kwargs)
        context["api_gateway_route"] = (
            ApiGatewayAdditionalRoute.objects.filter(route_key=self.websocket_route_key)
            .select_related("api_gateway")
            .first()
        )
        context["channel_name"] = self.channel_name
        return context


class AppChannelWebSocketMixin(AddWebSocketRouteToContextMixin):
    """Adds the websocket setup where the route key and channel name are the name of the app containing the view
    that extends this class
    """

    request = None

    def get_context_data(self, **kwargs) -> dict:
        app_name = sys.modules[
            resolve(self.request.path_info).func.__module__
        ].__package__
        self.channel_name = app_name
        self.websocket_route_key = app_name

        return super().get_context_data(**kwargs)
