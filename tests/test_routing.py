"""Tests that go through the URL resolver and the whole middleware stack.

Most other tests call views with ``RequestFactory``, which skips middleware, CSRF and routing.
These use the test ``Client``, with CSRF checks switched on, against ``tests.urls``.
"""

import json

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse

from django_aws_api_gateway_websockets.models import (
    ApiGateway,
    ChannelPermission,
    WebSocketSession,
    WebSocketToken,
    hash_session_key,
)

GATEWAY_SECRET = "s3cr3t-" + "x" * 30


def _csrf_client():
    """A client that enforces CSRF checks and holds a valid CSRF token."""
    client = Client(enforce_csrf_checks=True)
    token = client.get(reverse("csrf")).json()["token"]
    return client, token


class RoutingSetupTestCase(TestCase):
    def test_the_url_configuration_exists_and_resolves_the_package_views(self):
        self.assertEqual("tests.urls", settings.ROOT_URLCONF)
        self.assertEqual("/ws/token/", reverse("ws-token"))
        self.assertEqual("/ws/connect", reverse("ws", kwargs={"route": "connect"}))
        self.assertEqual("ws", resolve("/ws/default").url_name)
        self.assertEqual({"route": "default"}, resolve("/ws/default").kwargs)

    def test_allowed_hosts_is_set_and_not_an_annotation(self):
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertIn("testserver", settings.ALLOWED_HOSTS)

    def test_the_database_is_in_memory(self):
        """No SQLite file is created in the project folder by running the tests."""
        from django.db import connection

        self.assertTrue(
            connection.creation.is_in_memory_db(connection.settings_dict["NAME"])
        )

    def test_the_project_passes_the_django_system_checks(self):
        """Runs every registered check, including this package's, through the real registry."""
        call_command("check")


class TokenEndpointRoutingTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="route-user", password="pw")

    def _post(self, client, token=None, **extra):
        headers = {"HTTP_X_CSRFTOKEN": token} if token else {}
        headers.update(extra)
        return client.post(reverse("ws-token"), **headers)

    def test_get_is_not_allowed(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        self.assertEqual(405, client.get(reverse("ws-token")).status_code)

    def test_post_without_a_csrf_token_is_rejected_even_when_logged_in(self):
        client, _ = _csrf_client()
        client.force_login(self.user)

        response = self._post(client)

        self.assertEqual(403, response.status_code)
        self.assertFalse(WebSocketToken.objects.exists())

    def test_post_with_a_wrong_csrf_token_is_rejected(self):
        client, _ = _csrf_client()
        client.force_login(self.user)

        response = self._post(client, token="x" * 64)

        self.assertEqual(403, response.status_code)
        self.assertFalse(WebSocketToken.objects.exists())

    def test_an_anonymous_post_with_a_valid_csrf_token_is_refused(self):
        client, token = _csrf_client()

        response = self._post(client, token=token)

        self.assertEqual(403, response.status_code)
        self.assertIn(b"Authentication required", response.content)

    def test_a_logged_in_post_with_a_valid_csrf_token_returns_a_token(self):
        client, token = _csrf_client()
        client.force_login(self.user)

        response = self._post(client, token=token)

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(64, len(body["token"]))
        self.assertEqual(60, body["expires_in"])
        stored = WebSocketToken.objects.get(token=body["token"])
        self.assertEqual(self.user, stored.user)
        # the stored value is a hash, never the raw session key
        self.assertEqual(
            hash_session_key(client.session.session_key), stored.session_key
        )
        self.assertNotEqual(client.session.session_key, stored.session_key)


class WebSocketViewRoutingTestCase(TestCase):
    """The view is csrf_exempt, because API Gateway cannot send a CSRF token."""

    def setUp(self):
        self.user = User.objects.create_user(username="ws-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="Routed Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )
        self.session = WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name="room-1",
            api_gateway=self.api_gateway,
            user=self.user,
        )
        self.client = Client(enforce_csrf_checks=True)

    def _headers(self, **overrides):
        headers = {
            "HTTP_HOST": "www.example.com",
            "HTTP_X_FORWARDED_FOR": "123.123.123.123",
            "HTTP_X_FORWARDED_PROTO": "https",
            "HTTP_CONNECTIONID": "CONNECTION-123",
            "HTTP_USER_AGENT": "Mozilla/5.0",
            "HTTP_X_AMZN_APIGATEWAY_API_ID": "APIGateway-1",
            "HTTP_X_AMZN_TRACE_ID": "123456787654",
            "HTTP_X_FORWARDED_PORT": "443",
            "HTTP_X_REAL_IP": "172.0.0.1",
        }
        headers.update(overrides)
        return headers

    def _post(self, body=None, route="default", **header_overrides):
        return self.client.post(
            reverse("ws", kwargs={"route": route}),
            data=json.dumps(body if body is not None else {"action": "chat"}),
            content_type="application/json",
            **self._headers(**header_overrides),
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_message_is_handled_without_a_csrf_token(self):
        response = self._post()

        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True}, response.json())

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_message_for_a_closed_session_is_refused_through_the_stack(self):
        WebSocketSession.objects.filter(pk=self.session.pk).update(connected=False)

        self.assertEqual(400, self._post().status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_request_without_the_gateway_headers_is_refused(self):
        response = self.client.post(
            reverse("ws", kwargs={"route": "default"}),
            data=json.dumps({"action": "chat"}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
        )

        self.assertEqual(400, response.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_request_naming_an_unregistered_gateway_is_refused(self):
        response = self._post(HTTP_X_AMZN_APIGATEWAY_API_ID="Unknown-Gateway")

        self.assertEqual(400, response.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_disconnect_is_handled_through_the_stack(self):
        response = self._post(route="disconnect", body={})

        self.assertEqual(200, response.status_code)
        self.session.refresh_from_db()
        self.assertFalse(self.session.connected)

    @override_settings(
        ALLOWED_HOSTS=["www.example.com"],
        WEBSOCKETS={"gateway_secret": GATEWAY_SECRET},
    )
    def test_the_gateway_secret_is_enforced_end_to_end(self):
        refused = self._post()
        wrong = self._post(HTTP_X_WS_GATEWAY_SECRET="wrong")
        accepted = self._post(HTTP_X_WS_GATEWAY_SECRET=GATEWAY_SECRET)

        self.assertEqual(403, refused.status_code)
        self.assertEqual(403, wrong.status_code)
        self.assertEqual(200, accepted.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_channel_rule_is_enforced_on_connect_through_the_stack(self):
        ChannelPermission.objects.create(
            channel_name="root", access=ChannelPermission.Access.SUPERUSER_ONLY
        )
        connect_headers = self._headers(
            HTTP_CONNECTIONID="CONNECTION-NEW",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_COOKIE="c=1",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="e",
            HTTP_SEC_WEBSOCKET_KEY="k",
            HTTP_SEC_WEBSOCKET_VERSION="1",
        )

        response = self.client.post(
            reverse("ws-open", kwargs={"route": "connect"}) + "?channel=root",
            data="{}",
            content_type="application/json",
            **connect_headers,
        )

        self.assertEqual(403, response.status_code)
        self.assertFalse(
            WebSocketSession.objects.filter(connection_id="CONNECTION-NEW").exists()
        )


class AdminRoutingTestCase(TestCase):
    """The admin pages render through the real URL resolver and templates."""

    MODEL_PAGES = [
        "apigateway",
        "apigatewayadditionalroute",
        "websocketsession",
        "websockettoken",
        "connectionratelimit",
        "channelpermission",
    ]

    def setUp(self):
        self.admin_user = User.objects.create_superuser("root", password="pw")
        self.client.force_login(self.admin_user)

    def _url(self, model, page="changelist", **kwargs):
        return reverse(
            f"admin:django_aws_api_gateway_websockets_{model}_{page}", kwargs=kwargs
        )

    def test_every_changelist_renders(self):
        for model in self.MODEL_PAGES:
            with self.subTest(model=model):
                self.assertEqual(200, self.client.get(self._url(model)).status_code)

    def test_every_changelist_can_be_searched(self):
        """The additional route admin raised FieldError on any search until REV-QUAL-013."""
        for model in self.MODEL_PAGES:
            with self.subTest(model=model):
                response = self.client.get(self._url(model), {"q": "report"})

                self.assertEqual(200, response.status_code)

    def test_a_search_on_additional_routes_finds_by_route_key(self):
        from django_aws_api_gateway_websockets.models import ApiGatewayAdditionalRoute

        gateway = ApiGateway.objects.create(
            api_name="Admin Gateway", target_base_endpoint="https://example.com/"
        )
        ApiGatewayAdditionalRoute.objects.create(
            api_gateway=gateway,
            name="Reports",
            route_key="quarterly-report",
            integration_url="https://example.com/report",
        )

        response = self.client.get(
            self._url("apigatewayadditionalroute"), {"q": "quarterly"}
        )

        self.assertContains(response, "quarterly-report")

    def test_the_session_admin_cannot_add_or_change(self):
        session = WebSocketSession.objects.create(connection_id="ADMIN-1")

        self.assertEqual(
            403, self.client.get(self._url("websocketsession", "add")).status_code
        )
        change = self.client.get(
            self._url("websocketsession", "change", object_id=session.pk)
        )
        self.assertEqual(200, change.status_code)  # viewable
        self.assertNotContains(change, 'name="_save"')  # but not editable

    def test_the_token_admin_never_shows_the_session_key_hash(self):
        token = WebSocketToken.generate_token(self.admin_user, "a-session-key")

        for page in (
            self.client.get(self._url("websockettoken")),
            self.client.get(self._url("websockettoken", "change", object_id=token.pk)),
        ):
            self.assertNotContains(page, token.session_key)
            self.assertNotContains(page, "a-session-key")

    def test_the_channel_permission_form_renders_with_its_rules(self):
        response = self.client.get(self._url("channelpermission", "add"))

        self.assertContains(response, "Channel permission rules")

    def test_view_only_staff_do_not_get_the_aws_actions(self):
        from django.contrib.auth.models import Permission

        staff = User.objects.create_user("viewer", password="pw", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="view_apigateway"))
        self.client.force_login(staff)

        response = self.client.get(self._url("apigateway"))

        self.assertEqual(200, response.status_code)
        self.assertNotContains(response, "Create API Gateway")

    def test_superusers_get_the_aws_actions(self):
        ApiGateway.objects.create(
            api_name="Action Gateway", target_base_endpoint="https://example.com/"
        )

        response = self.client.get(self._url("apigateway"))

        self.assertContains(response, "Create API Gateway")
        self.assertContains(response, "Create Custom Domain")


class MixinRoutingTestCase(TestCase):
    def test_the_app_channel_mixin_resolves_the_real_route(self):
        """The mixin calls resolve() on the request path, which needs real URLs."""
        from django.test import RequestFactory
        from django.views.generic import TemplateView

        from django_aws_api_gateway_websockets.mixins import AppChannelWebSocketMixin

        class PageView(AppChannelWebSocketMixin, TemplateView):
            template_name = "unused.html"

        request = RequestFactory().get(reverse("ws-token"))
        view = PageView()
        view.request = request

        context = view.get_context_data()

        # reverse("ws-token") is a WebSocketTokenView in this package
        self.assertEqual("django_aws_api_gateway_websockets", context["channel_name"])
