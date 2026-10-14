"""URL configuration for the test suite: the package's views as a project would route them."""

from django.contrib import admin
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie

from django_aws_api_gateway_websockets.views import WebSocketTokenView, WebSocketView


class ChatWebSocketView(WebSocketView):
    """A sample view with one handler, routed the way API Gateway calls it."""

    ALLOWED_HANDLERS = {"chat"}

    def chat(self, request, *args, **kwargs):
        return JsonResponse({"ok": True})


class OpenChatWebSocketView(ChatWebSocketView):
    """The same view without the one-time token, for tests that connect without a browser."""

    USE_WS_TOKEN = False


@ensure_csrf_cookie
def csrf(request):
    """Sets the CSRF cookie and returns a matching token, as a page with a form would."""
    return JsonResponse({"token": get_token(request)})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("csrf/", csrf, name="csrf"),
    path("ws/token/", WebSocketTokenView.as_view(), name="ws-token"),
    path("ws/<slug:route>", ChatWebSocketView.as_view(), name="ws"),
    path("open/<slug:route>", OpenChatWebSocketView.as_view(), name="ws-open"),
]
