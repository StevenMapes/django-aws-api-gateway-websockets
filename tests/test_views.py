import json

from django.http import HttpResponseBadRequest
from django.test import RequestFactory, SimpleTestCase

from django_aws_api_gateway_websockets import views


class WebSocketViewSimpleTestCase(SimpleTestCase):
    """For tests that do not require a DB"""

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_default_required_headers(self):
        self.assertEqual(
            [
                "Host",
                "X-Forwarded-For",
                "X-Forwarded-Proto",
                "Content-Length",
                "Connectionid",
                "User-Agent",
                "X-Amzn-Apigateway-Api-Id",
            ],
            views.WebSocketView.required_headers,
        )

    def test_additional_required_headers(self):
        self.assertEqual(
            [
                "Connection",
                "X-Amzn-Trace-Id",
                "X-Forwarded-Port",
                "X-Real-Ip",
            ],
            views.WebSocketView.additional_required_headers,
        )

    def test_default_required_connection_headers(self):
        self.assertEqual(
            [
                "Cookie",
                "Origin",
                "Sec-Websocket-Extensions",
                "Sec-Websocket-Key",
                "Sec-Websocket-Version",
            ],
            views.WebSocketView.required_connection_headers,
        )

    def test_default_expected_useragent_prefix(self):
        self.assertEqual(
            "AmazonAPIGateway_", views.WebSocketView.expected_useragent_prefix
        )

    def test_default_aws_api_gateway_id(self):
        self.assertIsNone(views.WebSocketView.aws_api_gateway_id)

    def test__debug_when_debug_is_false(self):
        view = views.WebSocketView()
        view.debug = False
        view._debug("A message")
        self.assertEqual([], view.debug_log)

    def test__debug_when_debug_is_true(self):
        """Should append to the debug log"""
        view = views.WebSocketView()
        view.debug = True
        view._debug("A message")
        self.assertEqual(["A message"], view.debug_log)
        view._debug("Another entry")
        self.assertEqual(["A message", "Another entry"], view.debug_log)

    def test_default_route_selection_key(self):
        self.assertEqual("action", views.WebSocketView.route_selection_key)

    def test_setup(self):
        """Ensure the setup is working as expected by turning on debug and looking for the records"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "", data=json.dumps(post_data), content_type="application/json"
        )

        view = views.WebSocketView()
        view.debug = True
        view.setup(request=request)

        self.assertEqual(["Within setup", "Setup completed"], view.debug_log)

    def test__return_bad_request(self):
        """Should log a warning message and return a HttpBadRequest object"""
        msg = "This is the reason for the bad request"
        request = self.factory.get("")
        obj = views.WebSocketView()
        res = obj._return_bad_request(msg)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)
