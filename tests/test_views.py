import json
from unittest.mock import ANY, MagicMock, patch

from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.auth.signals import user_logged_out
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseBadRequest, JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from django_aws_api_gateway_websockets import views
from django_aws_api_gateway_websockets.models import (
    GATEWAY_SECRET_HEADER,
    ApiGateway,
    ChannelPermission,
    ChannelPermissionRule,
    WebSocketSession,
    WebSocketToken,
    hash_session_key,
    hash_user_auth,
)


class WebSocketTokenViewIntegrationTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="token-view-user", password="password"
        )

    def test_post_requires_authenticated_user(self):
        request = self.factory.post("/ws-token/")
        request.user = AnonymousUser()
        request.session = MagicMock(session_key="session-key")

        response = views.WebSocketTokenView.as_view()(request)

        self.assertEqual(403, response.status_code)
        self.assertEqual(b"Authentication required", response.content)

    @patch("django_aws_api_gateway_websockets.views.WebSocketToken.generate_token")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken.check_rate_limit")
    def test_post_creates_session_when_missing(
        self,
        mocked_check_rate_limit,
        mocked_generate_token,
    ):
        mocked_check_rate_limit.return_value = True
        mocked_generate_token.return_value = MagicMock(token="a" * 64)

        request = self.factory.post("/ws-token/")
        request.user = self.user
        request.session = MagicMock(session_key=None)
        request.session.create.side_effect = lambda: setattr(
            request.session,
            "session_key",
            "new-session-key",
        )

        response = views.WebSocketTokenView.as_view()(request)

        self.assertEqual(200, response.status_code)
        request.session.create.assert_called_with()
        mocked_check_rate_limit.assert_called_with(
            self.user,
            max_tokens_per_minute=20,
        )
        mocked_generate_token.assert_called_with(
            user=self.user,
            session_key="new-session-key",
        )

    @patch("django_aws_api_gateway_websockets.views.WebSocketToken.check_rate_limit")
    def test_post_returns_forbidden_when_rate_limited(self, mocked_check_rate_limit):
        mocked_check_rate_limit.return_value = False

        request = self.factory.post("/ws-token/")
        request.user = self.user
        request.session = MagicMock(session_key="session-key")

        response = views.WebSocketTokenView.as_view()(request)

        self.assertEqual(403, response.status_code)
        self.assertEqual(b"Rate limit exceeded", response.content)

    @patch("django_aws_api_gateway_websockets.views.WebSocketToken.generate_token")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken.check_rate_limit")
    def test_post_returns_token_json(
        self,
        mocked_check_rate_limit,
        mocked_generate_token,
    ):
        mocked_check_rate_limit.return_value = True
        mocked_generate_token.return_value = MagicMock(token="b" * 64)

        request = self.factory.post("/ws-token/")
        request.user = self.user
        request.session = MagicMock(session_key="session-key")

        response = views.WebSocketTokenView.as_view()(request)

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"token": "b" * 64, "expires_in": 60},
            json.loads(response.content),
        )


class WebSocketViewSecuritySimpleTestCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_debug_sanitizes_and_truncates_message(self):
        view = views.WebSocketView(debug=True)

        view._debug("<script>" + ("x" * 600))

        self.assertIn("&lt;script&gt;", view.debug_log[0])
        self.assertLessEqual(len(view.debug_log[0]), 520)

    def test_setup_ignores_body_when_too_large(self):
        request = self.factory.post(
            "/",
            data="x" * (views.WebSocketView.MAX_BODY_SIZE + 1),
            content_type="application/json",
        )

        view = views.WebSocketView(debug=True)
        view.setup(request)

        self.assertEqual({}, view.body)
        self.assertIn("Request body too large", view.debug_log)

    def test_setup_uses_empty_body_for_invalid_json(self):
        request = self.factory.post(
            "/",
            data="{invalid-json",
            content_type="application/json",
        )

        view = views.WebSocketView(debug=True)
        view.setup(request)

        self.assertEqual({}, view.body)
        self.assertIn("Body is invalid JSON", view.debug_log)

    def test_validate_connection_id_rejects_empty_id(self):
        view = views.WebSocketView()

        self.assertFalse(view._validate_connection_id(""))

    def test_validate_connection_id_rejects_long_id(self):
        view = views.WebSocketView()

        self.assertFalse(view._validate_connection_id("a" * 129))

    def test_validate_connection_id_rejects_invalid_characters(self):
        view = views.WebSocketView()

        self.assertFalse(view._validate_connection_id("abc<script>"))

    def test_validate_connection_id_accepts_allowed_characters(self):
        view = views.WebSocketView()

        self.assertTrue(view._validate_connection_id("abcABC123_=-"))

    def test_get_client_ip_uses_first_forwarded_ip(self):
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="192.168.1.10, 10.0.0.1",
        )
        view = views.WebSocketView()

        self.assertEqual("192.168.1.10", view._get_client_ip(request))

    def test_get_client_ip_falls_back_to_remote_addr(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="192.168.1.11",
        )
        view = views.WebSocketView()

        self.assertEqual("192.168.1.11", view._get_client_ip(request))

    def test_get_client_ip_returns_default_for_invalid_ip(self):
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="not-an-ip",
        )
        view = views.WebSocketView(debug=True)

        self.assertEqual("0.0.0.0", view._get_client_ip(request))
        self.assertIn("Invalid IP address: not-an-ip", view.debug_log)


class WebSocketViewAdditionalIntegrationTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.api_gateway = ApiGateway.objects.create(
            api_name="View Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
            default_channel_name="default-channel",
        )

    def test_get_channel_name_raises_value_error_for_invalid_channel(self):
        request = self.factory.get("/", {"channel": "bad channel"})
        view = views.WebSocketView(api_gateway=self.api_gateway)

        with self.assertRaises(ValueError):
            view._get_channel_name(request)

    def test_get_channel_name_raises_value_error_for_too_long_channel(self):
        request = self.factory.get("/", {"channel": "a" * 192})
        view = views.WebSocketView(api_gateway=self.api_gateway)

        with self.assertRaises(ValueError):
            view._get_channel_name(request)

    def test_max_channel_name_length_matches_the_database_column(self):
        """A name that passes validation must fit in WebSocketSession.channel_name"""
        column = WebSocketSession._meta.get_field("channel_name")

        self.assertEqual(column.max_length, views.WebSocketView.MAX_CHANNEL_NAME_LENGTH)

    def test_get_channel_name_rejects_a_channel_longer_than_the_column(self):
        request = self.factory.get("/", {"channel": "a" * 129})
        view = views.WebSocketView(api_gateway=self.api_gateway)

        with self.assertRaises(ValueError):
            view._get_channel_name(request)

    def test_get_channel_name_accepts_a_channel_as_long_as_the_column(self):
        request = self.factory.get("/", {"channel": "a" * 128})
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertEqual("a" * 128, view._get_channel_name(request))

    def test_get_channel_name_uses_api_gateway_default(self):
        request = self.factory.get("/")
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertEqual("default-channel", view._get_channel_name(request))


class WebSocketViewSimpleTestCase(SimpleTestCase):
    """For tests that do not require a DB"""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        # These tests use no database, so the default can_join_channel must not look up a
        # ChannelPermission row. No row means the channel is open.
        patcher = patch.object(
            views.WebSocketView, "get_channel_permission", return_value=None
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_change_channel_updates_websocket_session_channel_name(self):
        request = self.factory.post("/")
        websocket_session = MagicMock(channel_name="old-channel")

        view = views.WebSocketView()
        view.websocket_session = websocket_session
        view.body = {"channel": "new-channel"}

        response = view.change_channel(request)

        self.assertIsNone(response)
        self.assertEqual("new-channel", websocket_session.channel_name)
        websocket_session.save.assert_called_once_with(
            update_fields=["channel_name", "updated_on"]
        )

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
        obj = views.WebSocketView()
        res = obj._return_bad_request(msg)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)

    @patch("django_aws_api_gateway_websockets.views.warnings")
    def test_route_selection_key_missing(self, mock_warnings):
        """Ensure the expected response is generated when the route selection key is missing"""
        obj = views.WebSocketView()
        res = obj.route_selection_key_missing(None)

        mock_warnings.warn.assert_called_with(
            "Deprecated: Use handler_selection_key_missing instead. Will be removed in version 3",
            DeprecationWarning,
            stacklevel=2,
        )
        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)
        self.assertEqual(
            b"route_select_key action missing from request body.", res.content
        )

    def test_handler_selection_key_missing_missing(self):
        """Ensure the expected response is generated when the handler selection key is missing"""
        obj = views.WebSocketView()
        res = obj.handler_selection_key_missing(None)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)
        self.assertEqual(b"Invalid request format (1)", res.content)

    def test_missing_headers(self):
        """Ensure the expected response is generated when there are missing headers"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "", data=json.dumps(post_data), content_type="application/json"
        )

        obj = views.WebSocketView()
        res = obj.missing_headers(request=request)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)
        self.assertEqual(b"Invalid request headers", res.content)

    def test_invalid_useragent(self):
        """Ensure the expected response is generated when the useragent is invalid"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0",
        )

        obj = views.WebSocketView()
        res = obj.invalid_useragent(request=request)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)
        self.assertEqual(b"Unexpected Useragent", res.content)

    def test__expected_headers(self):
        """Ensure the methods returns True when all headers are present otherwise should return False"""
        post_data = {"action": "default", "key": "value"}

        test_headers = [
            {
                "required": ["My-Expected-Header", "Another-Header"],
                "additional_required": ["X-Amzn-Trace-Id", "Connection"],
                "supplied": {
                    "HTTP_My_Expected_Header": "some value",
                    "HTTP_X_Amzn_Trace_Id": "err-gf234",
                    "HTTP_Connection": "SFfgGFG",
                },
                "expected_result": False,
            },
            {
                "required": ["My-Expected-Header", "Another-Header"],
                "additional_required": ["X-Amzn-Trace-Id", "Connection"],
                "supplied": {
                    "HTTP_My_Expected_Header": "some value",
                    "HTTP_Another_Header": "some value",
                    "HTTP_X_Amzn_Trace_Id": "err-gf234",
                    "HTTP_Connection": "SFfgGFG",
                },
                "expected_result": True,
            },
        ]
        for headers in test_headers:
            with self.subTest(headers=headers):
                obj = views.WebSocketView()
                obj.required_headers = headers["required"]
                obj.additional_required_headers = headers["additional_required"]
                request = self.factory.post(
                    "",
                    data=json.dumps(post_data),
                    content_type="application/json",
                    HTTP_USER_AGENT="Mozilla/5.0",
                    **headers["supplied"],
                )

                self.assertEqual(
                    headers["expected_result"], obj._expected_headers(request=request)
                )

    @patch("django_aws_api_gateway_websockets.views.ApiGateway")
    def test_apigateway_check_when_db_record_matches_header_and_class_attribute_is_not_set_return_true(
        self, MockApiGateway
    ):
        """
        When the class does not have an aws_api_gateway_id attribute set
        and the X_Amzn_Apigateway_Api_Id header DOES MATCH a database record

        The method should return True I.E accept the request as it's from an expected API Gateway endpoint

        :param MockApiGateway:
        :return:
        """
        allowed_api_id = "ABC123AB"
        api_gateway = MagicMock(api_id=allowed_api_id)
        MockApiGateway.objects.filter.return_value.first.return_value = api_gateway

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id=allowed_api_id,
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = None
        obj._allowed_apigateway(request)

        MockApiGateway.objects.filter.assert_called_with(
            api_id=request.headers["X-Amzn-Apigateway-Api-Id"]
        )
        MockApiGateway.objects.filter.return_value.first.assert_called_with()
        self.assertTrue(obj._allowed_apigateway(request=request))

    @patch("django_aws_api_gateway_websockets.views.ApiGateway")
    def test_apigateway_check_when_db_record_does_not_match_header_and_class_attribute_is_not_set_return_false(
        self, MockApiGateway
    ):
        """
        When the class does not have an aws_api_gateway_id attribute set
        and the X_Amzn_Apigateway_Api_Id header does not match ANY database record

        The method should return False I.E do not accept the request
        """
        MockApiGateway.objects.filter.return_value.first.return_value = None

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="some-other-api-gatewway",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = None
        obj._allowed_apigateway(request)

        MockApiGateway.objects.filter.assert_called_with(
            api_id=request.headers["X-Amzn-Apigateway-Api-Id"]
        )
        MockApiGateway.objects.filter.return_value.first.assert_called_with()

        self.assertFalse(obj._allowed_apigateway(request=request))

    @patch("django_aws_api_gateway_websockets.views.ApiGateway")
    def test_apigateway_check_when_db_record_matches_header_and_the_class_attribute_return_true(
        self, MockApiGateway
    ):
        """
        When the class has an aws_api_gateway_id attribute set and it matches BOTH the header and the DB record

        The method should return True I.E accept the request as it's from an expected API Gateway endpoint

        :param MockApiGateway:
        :return:
        """
        allowed_api_id = "ABC123AB"
        api_gateway = MagicMock(api_id=allowed_api_id)
        MockApiGateway.objects.filter.return_value.first.return_value = api_gateway

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id=allowed_api_id,
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id
        obj._allowed_apigateway(request)

        MockApiGateway.objects.filter.assert_called_with(
            api_id=request.headers["X-Amzn-Apigateway-Api-Id"]
        )
        MockApiGateway.objects.filter.return_value.first.assert_called_with()
        self.assertTrue(obj._allowed_apigateway(request=request))

    @patch("django_aws_api_gateway_websockets.views.ApiGateway")
    def test_apigateway_no_db_match_found_and_class_attribute_not_matched_return_false(
        self, MockApiGateway
    ):
        """
        When the class has an aws_api_gateway_id attribute set but it does not match the header
        And the DB check also does not match

        Return False
        """
        MockApiGateway.objects.filter.return_value.first.return_value = None

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="some-other-api-gatewway",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = "some-other-id"
        obj._allowed_apigateway(request)

        MockApiGateway.objects.filter.assert_called_with(
            api_id=request.headers["X-Amzn-Apigateway-Api-Id"]
        )
        MockApiGateway.objects.filter.return_value.first.assert_called_with()

        self.assertFalse(obj._allowed_apigateway(request=request))

    @patch("django_aws_api_gateway_websockets.views.ApiGateway")
    def test_apigateway_with_db_match_but_class_attribute_not_matched_return_false(
        self, MockApiGateway
    ):
        """
        When the class has an aws_api_gateway_id attribute set but it does not match the header

        The method should return False even if the DB record matches
        """
        allowed_api_id = "ABC123AB"
        api_gateway = MagicMock(api_id=allowed_api_id)
        MockApiGateway.objects.filter.return_value.first.return_value = api_gateway

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id=allowed_api_id,
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = "some-other-id"
        obj._allowed_apigateway(request)

        MockApiGateway.objects.filter.assert_called_with(
            api_id=request.headers["X-Amzn-Apigateway-Api-Id"]
        )
        MockApiGateway.objects.filter.return_value.first.assert_called_with()

        self.assertFalse(obj._allowed_apigateway(request=request))

    # _expected_useragent
    #
    # API Gateway calls Django with its own User-Agent, AmazonAPIGateway_<api id>, on the
    # $connect route only. Messages and $disconnect carry the client's real User-Agent.

    def _ua_request(self, user_agent=None, api_id="ABC123AB"):
        extra = {"HTTP_X_AMZN_APIGATEWAY_API_ID": api_id}
        if user_agent is not None:
            extra["HTTP_USER_AGENT"] = user_agent
        return self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            **extra,
        )

    def _ua_view(self, route, pinned_id=None, registered_id="ABC123AB"):
        view = views.WebSocketView()
        view.kwargs = {"route": route}
        view.aws_api_gateway_id = pinned_id
        view.api_gateway = MagicMock(api_id=registered_id) if registered_id else None
        return view

    def test__expected_useragent_connect_accepts_the_gateways_own_useragent(self):
        view = self._ua_view("connect")

        self.assertTrue(
            view._expected_useragent(self._ua_request("AmazonAPIGateway_ABC123AB"))
        )

    def test__expected_useragent_connect_rejects_a_real_clients_useragent(self):
        view = self._ua_view("connect")

        for user_agent in ("Mozilla/5.0", "curl/8.0", "", None):
            with self.subTest(user_agent=user_agent):
                self.assertFalse(view._expected_useragent(self._ua_request(user_agent)))

    def test__expected_useragent_connect_rejects_another_gateways_useragent(self):
        view = self._ua_view("connect")

        self.assertFalse(
            view._expected_useragent(self._ua_request("AmazonAPIGateway_OTHERID"))
        )

    def test__expected_useragent_connect_requires_an_exact_match(self):
        view = self._ua_view("connect")

        for user_agent in (
            "AmazonAPIGateway_ABC123AB-extra",
            "AmazonAPIGateway_ABC123A",
            "xAmazonAPIGateway_ABC123AB",
            "amazonapigateway_abc123ab",
            "Mozilla/5.0 AmazonAPIGateway_ABC123AB",
        ):
            with self.subTest(user_agent=user_agent):
                self.assertFalse(view._expected_useragent(self._ua_request(user_agent)))

    def test__expected_useragent_connect_uses_the_pinned_gateway_id(self):
        view = self._ua_view("connect", pinned_id="PINNED1", registered_id=None)

        self.assertTrue(
            view._expected_useragent(
                self._ua_request("AmazonAPIGateway_PINNED1", api_id="PINNED1")
            )
        )
        self.assertFalse(
            view._expected_useragent(
                self._ua_request("AmazonAPIGateway_ABC123AB", api_id="PINNED1")
            )
        )

    def test__expected_useragent_connect_without_a_registered_gateway_uses_the_header_id(
        self,
    ):
        view = self._ua_view("connect", registered_id=None)

        self.assertTrue(
            view._expected_useragent(self._ua_request("AmazonAPIGateway_ABC123AB"))
        )
        self.assertFalse(view._expected_useragent(self._ua_request("Mozilla/5.0")))

    def test__expected_useragent_connect_honours_a_custom_prefix(self):
        view = self._ua_view("connect")
        view.expected_useragent_prefix = "MyGateway/"

        self.assertTrue(
            view._expected_useragent(self._ua_request("MyGateway/ABC123AB"))
        )
        self.assertFalse(
            view._expected_useragent(self._ua_request("AmazonAPIGateway_ABC123AB"))
        )

    def test__expected_useragent_connect_with_no_gateway_id_at_all_is_rejected(self):
        view = self._ua_view("connect", registered_id=None)
        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_USER_AGENT="AmazonAPIGateway_ABC123AB",
        )

        self.assertFalse(view._expected_useragent(request))

    def test__expected_useragent_accepts_a_real_useragent_on_message_and_disconnect(
        self,
    ):
        """The client's own User-Agent is forwarded on these routes, whatever it is."""
        for route in ("disconnect", "chat", "default"):
            for pinned_id in (None, "ABC123AB"):
                for user_agent in ("Mozilla/5.0", "curl/8.0", "okhttp/4.9", ""):
                    with self.subTest(
                        route=route, pinned_id=pinned_id, user_agent=user_agent
                    ):
                        view = self._ua_view(route, pinned_id=pinned_id)

                        self.assertTrue(
                            view._expected_useragent(self._ua_request(user_agent))
                        )

    def test__expected_useragent_does_not_fail_when_a_client_sends_no_useragent(self):
        for route in ("disconnect", "chat"):
            with self.subTest(route=route):
                view = self._ua_view(route)

                self.assertTrue(view._expected_useragent(self._ua_request(None)))

    def test__expected_useragent_reads_the_route_from_the_arguments_too(self):
        view = views.WebSocketView()
        view.api_gateway = MagicMock(api_id="ABC123AB")

        self.assertFalse(
            view._expected_useragent(self._ua_request("Mozilla/5.0"), route="connect")
        )
        self.assertTrue(
            view._expected_useragent(self._ua_request("Mozilla/5.0"), route="chat")
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test__check_allowed_hosts__when_host_is_allowed__return_true(self):
        """When the host of the request is within the allowed hosts of settings.py True should be returned"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"Mozzila/5.0",
            HTTP_HOST="www.example.com",
        )

        obj = views.WebSocketView()

        self.assertTrue(obj._check_allowed_hosts(request=request))

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test__check_allowed_hosts__when_host_is_not_allowed__return_false(self):
        """When the host of the request is within the allowed hosts of settings.py False should be returned"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"Mozzila/5.0",
            HTTP_HOST="www.anotherdomain.com",
        )

        obj = views.WebSocketView()

        self.assertFalse(obj._check_allowed_hosts(request=request))

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test__check_host_is_in_origin__when_it_iss(self):
        """When the host of the request is within the origin of the request True should be returned"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"Mozzila/5.0",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.example.com",
        )

        obj = views.WebSocketView()

        self.assertTrue(obj._check_host_is_in_origin(request=request))

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test__check_host_is_in_origin__when_it_is_not(self):
        """When the host of the request is NOT ithin the origin of the request False should be returned"""
        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"Mozzila/5.0",
            HTTP_HOST="www.anotherdomain.com",
            HTTP_ORIGIN="http://www.example.com",
        )

        obj = views.WebSocketView()

        self.assertFalse(obj._check_host_is_in_origin(request=request))

    def test_the_automatic_handler_list_has_the_plain_methods_of_the_subclass(self):
        class ChatView(views.WebSocketView):
            def chat(self, request, *args, **kwargs):
                return None

            def _private(self):
                return None

        self.assertEqual({"default", "chat"}, ChatView().ALLOWED_HANDLERS)

    def test_the_automatic_handler_list_leaves_out_overridden_hooks(self):
        """Hooks a view overrides are not handlers a client can name"""

        class HookView(views.WebSocketView):
            def can_join_channel(self, request, channel_name):
                return True

            def get_channel_permission(self, channel_name):
                return None

            def has_any_permission(self, request):
                return True

            def connect(self, request, *args, **kwargs):
                return None

            def disconnect(self, request, *args, **kwargs):
                return None

            def session_not_found(self, request, *args, **kwargs):
                return None

            def chat(self, request, *args, **kwargs):
                return None

        self.assertEqual({"default", "chat"}, HookView().ALLOWED_HANDLERS)

    def test_the_automatic_handler_list_keeps_default_and_change_channel(self):
        class ChatView(views.WebSocketView):
            def default(self, request, *args, **kwargs):
                return None

            def change_channel(self, request, *args, **kwargs):
                return super().change_channel(request, *args, **kwargs)

        self.assertEqual({"default", "change_channel"}, ChatView().ALLOWED_HANDLERS)

    def test_the_automatic_handler_list_leaves_out_things_that_are_not_plain_functions(
        self,
    ):
        class Model:
            pass

        class ChatView(views.WebSocketView):
            model = Model
            helper = staticmethod(lambda: None)
            callable_instance = MagicMock()

            @classmethod
            def build(cls, request, *args, **kwargs):
                return None

            @property
            def computed(self):
                return None

            def chat(self, request, *args, **kwargs):
                return None

        self.assertEqual({"default", "chat", "helper"}, ChatView().ALLOWED_HANDLERS)

    def test_an_explicit_allow_list_is_used_exactly_as_given(self):
        class ChatView(views.WebSocketView):
            ALLOWED_HANDLERS = {"connect", "chat"}

        self.assertEqual({"connect", "chat"}, ChatView().ALLOWED_HANDLERS)

    def test_additional_allowed_handlers_are_still_added(self):
        class ChatView(views.WebSocketView):
            ADDITIONAL_ALLOWED_HANDLERS = ["change_channel"]

            def chat(self, request, *args, **kwargs):
                return None

        self.assertEqual(
            {"default", "change_channel", "chat"}, ChatView().ALLOWED_HANDLERS
        )

    def _origin_check(self, host, origin):
        headers = {"HTTP_HOST": host}
        if origin is not None:
            headers["HTTP_ORIGIN"] = origin
        request = self.factory.post("", **headers)
        return views.WebSocketView()._check_host_is_in_origin(request=request)

    def test__check_host_is_in_origin__accepts_the_same_host(self):
        for host, origin in (
            ("www.example.com", "https://www.example.com"),
            ("www.example.com", "http://www.example.com"),
            ("WWW.Example.com", "https://www.EXAMPLE.com"),
            ("www.example.com", "https://www.example.com:443"),
            ("www.example.com:8000", "http://www.example.com:8000"),
            ("localhost:8000", "http://localhost:8000"),
            ("[::1]:8000", "http://[::1]:8000"),
        ):
            with self.subTest(host=host, origin=origin):
                self.assertTrue(self._origin_check(host, origin))

    def test__check_host_is_in_origin__accepts_a_sub_domain_of_the_host(self):
        """A site on www.example.com may connect to an app at example.com"""
        for host, origin in (
            ("example.com", "https://www.example.com"),
            ("example.com", "https://a.b.example.com"),
            ("example.com:8000", "http://app.example.com:8000"),
        ):
            with self.subTest(host=host, origin=origin):
                self.assertTrue(self._origin_check(host, origin))

    def test__check_host_is_in_origin__refuses_a_look_alike_origin(self):
        for host, origin in (
            ("www.example.com", "https://www.example.com.attacker.net"),
            ("example.com", "https://notexample.com"),
            ("example.com", "https://example.com.attacker.net"),
            ("www.example.com", "https://evil.net/?www.example.com"),
            ("www.example.com", "https://evil.net/www.example.com"),
            ("www.example.com", "https://evil.net#www.example.com"),
            ("www.example.com", "https://www.example.com@evil.net"),
            ("www.example.com", "https://evil.net:443@www.example.com.evil.net"),
            ("www.example.com", "https://example.com"),  # a parent of the host
        ):
            with self.subTest(host=host, origin=origin):
                self.assertFalse(self._origin_check(host, origin))

    def test__check_host_is_in_origin__refuses_a_different_port(self):
        for host, origin in (
            ("www.example.com:8000", "http://www.example.com:9000"),
            ("www.example.com:8000", "http://www.example.com"),
            ("www.example.com", "https://www.example.com:8443"),
        ):
            with self.subTest(host=host, origin=origin):
                self.assertFalse(self._origin_check(host, origin))

    def test__check_host_is_in_origin__refuses_an_origin_that_is_not_http_or_https(
        self,
    ):
        for origin in (
            "null",
            "",
            "www.example.com",
            "ftp://www.example.com",
            "file://www.example.com",
            "ws://www.example.com",
            "javascript:www.example.com",
            "https://",
        ):
            with self.subTest(origin=origin):
                self.assertFalse(self._origin_check("www.example.com", origin))

    def test__check_host_is_in_origin__refuses_a_missing_origin_or_host(self):
        self.assertFalse(self._origin_check("www.example.com", None))
        request = self.factory.post("", HTTP_ORIGIN="https://www.example.com")
        request.META.pop("HTTP_HOST", None)
        self.assertFalse(views.WebSocketView._check_host_is_in_origin(request))

    def test__expected_connection_headers(self):
        """Ensure the methods returns True when all headers are present otherwise should return False"""
        post_data = {"action": "default", "key": "value"}

        test_headers = [
            {
                "name": "All expected headers",
                "required_connection_headers": [
                    "Cookie",
                    "Origin",
                    "Sec-Websocket-Extensions",
                    "Sec-Websocket-Key",
                    "Sec-Websocket-Version",
                ],
                "supplied": {
                    "HTTP_Cookie": "some-cookie",
                    "HTTP_Origin": "example.com",
                    "HTTP_Sec-Websocket-Extensions": "some-value",
                    "HTTP_Sec-Websocket-Key": "some-key",
                    "HTTP_Sec-Websocket-Version": "1.2.3",
                },
                "expected_result": True,
            },
            {
                "name": "Missing a header",
                "required_connection_headers": [
                    "Cookie",
                    "Origin",
                    "Sec-Websocket-Extensions",
                    "Sec-Websocket-Key",
                    "Sec-Websocket-Version",
                ],
                "supplied": {
                    "HTTP_Cookie": "some-cookie",
                    "HTTP_Origin": "example.com",
                    "HTTP_Sec-Websocket-Extensions": "some-value",
                    "HTTP_Sec-Websocket-Key": "some-key",
                },
                "expected_result": False,
            },
        ]
        for headers in test_headers:
            with self.subTest(headers=headers):
                obj = views.WebSocketView()
                obj.required_connection_headers = headers["required_connection_headers"]
                request = self.factory.post(
                    "",
                    data=json.dumps(post_data),
                    content_type="application/json",
                    HTTP_USER_AGENT="Mozilla/5.0",
                    **headers["supplied"],
                )

                self.assertEqual(
                    headers["expected_result"],
                    obj._expected_connection_headers(request=request),
                    headers["name"],
                )

    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test__add_user_to_request_when_session_not_found(self, MockWebSocketSession):
        """A session that can not be found is handled, and the request keeps its user"""
        chain = MockWebSocketSession.objects.select_related.return_value
        chain.filter.return_value.first.return_value = None
        con_id = "ABC123xyz_-="

        obj = views.WebSocketView()
        obj.debug = True
        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid=con_id,
        )

        self.assertFalse(hasattr(request, "user"))

        self.assertTrue(obj._add_user_to_request(request))

        MockWebSocketSession.objects.select_related.assert_called_with("user")
        chain.filter.assert_called_with(
            connection_id=con_id, connected=True, api_gateway=None
        )
        MockWebSocketSession.objects.filter.assert_not_called()
        self.assertFalse(hasattr(request, "user"))
        self.assertIn(f"Session not found: {con_id}", obj.debug_log)

    @patch("django_aws_api_gateway_websockets.views.F")
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test__add_user_to_request_when_session_found(
        self, MockWebSocketSession, mock_F
    ):
        """The user is added to the request if one is set against the loaded session, and
        the request is counted with one UPDATE on the session's primary key"""
        mocked_user = MagicMock(pk=12)
        configs = [
            {"name": "No User in session", "user": None},
            {"name": "User set in session", "user": mocked_user},
        ]

        for config in configs:
            with self.subTest(config=config):
                MockWebSocketSession.reset_mock()
                wss = MagicMock(
                    pk=5, user=config["user"], connection_id="12345", auth_hash=""
                )
                obj = views.WebSocketView()
                obj.websocket_session = wss
                request = self.factory.post(
                    "",
                    data=json.dumps({}),
                    content_type="application/json",
                    HTTP_Connectionid="12345",
                )

                self.assertFalse(hasattr(request, "user"))
                self.assertTrue(obj._add_user_to_request(request))

                # The loaded session is used, and nothing is fetched again or locked
                MockWebSocketSession.objects.select_related.assert_not_called()
                MockWebSocketSession.objects.select_for_update.assert_not_called()
                MockWebSocketSession.objects.filter.assert_called_once_with(pk=5)
                MockWebSocketSession.objects.filter.return_value.update.assert_called_once_with(
                    request_count=mock_F.return_value.__add__.return_value
                )

                if config["user"]:
                    self.assertEqual(mocked_user, request.user)
                else:
                    self.assertFalse(hasattr(request, "user"))

    def test__get_channel_name(self):
        """Ensure the method returns the channel either from the GET string of set against the API Gateway"""
        api_gateway = ApiGateway(default_channel_name="default channel")
        configs = [
            {
                "name": "channel in url only",
                "qs": "channel=my-channel",
                "channel": "my-channel",
                "db": False,
            },
            {
                "name": "channel in url and db",
                "qs": "channel=my-channel",
                "channel": "my-channel",
                "db": True,
            },
            {
                "name": "channel db only",
                "qs": "",
                "channel": "default channel",
                "db": True,
            },
            {"name": "no channel", "qs": "", "channel": "", "db": False},
        ]

        for config in configs:
            with self.subTest(config=config):
                obj = views.WebSocketView()
                if config["db"]:
                    obj.api_gateway = api_gateway

                request = self.factory.post(
                    f"?{config['qs']}",
                    data=json.dumps({}),
                    content_type="application/json",
                )

                res = obj._get_channel_name(request)

                self.assertEqual(config["channel"], res, config["name"])

    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test__load_session(self, MockWebSocketSession):
        """Ensure the WebSocketSession is fetched from the DB and set against the websocket_session class attribute"""
        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
        )
        obj = views.WebSocketView()
        obj.api_gateway = None

        self.assertTrue(obj._load_session(request))

        MockWebSocketSession.objects.select_related.assert_called_with("user")
        chain = MockWebSocketSession.objects.select_related.return_value
        chain.filter.assert_called_with(
            connection_id="1234", connected=True, api_gateway=None
        )
        self.assertEqual(
            obj.websocket_session, chain.filter.return_value.first.return_value
        )

    def test__additional_connection_checks(self):
        """The _additional_connection_checks method should return True, "" for the default implementation"""
        obj = views.WebSocketView()
        result, msg = obj._additional_connection_checks(None)
        self.assertTrue(result)
        self.assertEqual("", msg)

    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test_disconnect(self, MockWebSocketSession):
        """The disconnect method should update only the connected flag, with one query"""
        MockWebSocketSession.objects.filter.return_value.update.return_value = 1

        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
        )
        obj = views.WebSocketView()

        res = obj.disconnect(request)

        self.assertIsNone(res)
        MockWebSocketSession.objects.filter.assert_called_with(
            connection_id=request.headers["Connectionid"], api_gateway=None
        )
        update = MockWebSocketSession.objects.filter.return_value.update
        update.assert_called_once()
        self.assertFalse(update.call_args.kwargs["connected"])
        self.assertIn("updated_on", update.call_args.kwargs)

    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test_disconnect_is_scoped_to_the_calling_gateway(self, MockWebSocketSession):
        """A request from one gateway cannot disconnect a session on another"""
        MockWebSocketSession.objects.filter.return_value.update.return_value = 1
        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
        )
        gateway = MagicMock()
        obj = views.WebSocketView(api_gateway=gateway)

        obj.disconnect(request)

        MockWebSocketSession.objects.filter.assert_called_with(
            connection_id="1234", api_gateway=gateway
        )

    def test_default(self):
        """The method handling default actions should raise a NotImplemented error by default"""
        obj = views.WebSocketView()

        with self.assertRaises(NotImplementedError) as e:
            obj.default(request=self.factory.get(""))
        self.assertEqual(
            "This logic needs to be defined within the subclass", str(e.exception)
        )

    @override_settings(
        ALLOWED_HOSTS=["www.example.com"],
        WEBSOCKETS={"rate_limit_max_attempts": 20, "rate_limit_window_minutes": 1},
    )
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect(
        self,
        MockWebSocketToken,
        MockConnectionRateLimit,
        MockJsonResponse,
        MockWebSocketSession,
    ):
        """Test the connect method when the expected header are set. Should pass through all checks"""
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 100)

        user = MagicMock(is_authenticated=True)
        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.example.com",
        )
        request.user = user
        request.session = MagicMock()
        obj = views.WebSocketView()

        res = obj.connect(request)

        MockConnectionRateLimit.check_rate_limit.assert_called_with(
            ip_address="127.0.0.1",
            user=user,
            max_attempts=20,
            window_minutes=1,
        )
        self.assertEqual(1, MockWebSocketToken.validate_and_consume.call_count)
        MockConnectionRateLimit.record_attempt("127.0.0.1", user, successful=True)

        MockWebSocketSession.objects.create.assert_called_with(
            connection_id=request.headers["Connectionid"],
            channel_name=obj._get_channel_name(request),
            user=request.user if request.user.is_authenticated else None,
            api_gateway=obj.api_gateway,
            session_key_hash=ANY,
            auth_hash=ANY,
        )
        MockJsonResponse.assert_called_with({})
        self.assertEqual(MockJsonResponse.return_value, res)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect__missing_expected_headers(
        self,
        MockWebSocketToken,
        MockConnectionRateLimit,
        MockHttpResponseBadRequest,
        MockJsonResponse,
        MockWebSocketSession,
    ):
        """Test the connect method when the expected headers are missing."""
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 100)

        user = MagicMock(is_authenticated=True)
        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Origin="example.com",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.example.com",
        )
        request.user = user
        request.session = MagicMock()
        obj = views.WebSocketView()

        res = obj.connect(request)

        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockWebSocketSession.objects.create.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        MockHttpResponseBadRequest.assert_called_with("Missing 3 headers")

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect__with_invalid_host(
        self,
        MockWebSocketToken,
        MockConnectionRateLimit,
        MockHttpResponseBadRequest,
        MockJsonResponse,
        MockWebSocketSession,
    ):
        """Test the connect method when the host is not in the allowed list are missing."""
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 100)

        user = MagicMock(is_authenticated=True)
        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Origin="example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
            HTTP_HOST="www.spoofed.com",
            HTTP_ORIGIN="https://www.spoofed.com",
        )
        request.user = user
        request.session = MagicMock()
        obj = views.WebSocketView()

        res = obj.connect(request)

        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockWebSocketSession.objects.create.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        MockHttpResponseBadRequest.assert_called_with(
            (f"Host is not in AllowedHosts ['www.example.com']")
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect__with_host_not_in_origin(
        self,
        MockWebSocketToken,
        MockConnectionRateLimit,
        MockHttpResponseBadRequest,
        MockJsonResponse,
        MockWebSocketSession,
    ):
        """Test the connect method when the host does not exist within the origin."""
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 100)

        user = MagicMock(is_authenticated=True)
        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Origin="example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.spoofed.com",
        )
        request.user = user
        request.sesssion = MagicMock()
        obj = views.WebSocketView()

        res = obj.connect(request)

        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockWebSocketSession.objects.create.call_count)
        MockHttpResponseBadRequest.assert_called_with("Host is not in Origin")
        self.assertEqual(0, MockJsonResponse.call_count)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect__additional_connection_checks_returns_false(
        self,
        MockWebSocketToken,
        MockConnectionRateLimit,
        MockHttpResponseBadRequest,
        MockJsonResponse,
        MockWebSocketSession,
    ):
        """Test the connect method when the expected headers are missing."""
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 100)

        user = MagicMock(is_authenticated=True)
        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Origin="example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.example.com",
        )
        request.session = MagicMock()
        request.user = user

        class SubClassedView(views.WebSocketView):
            def _additional_connection_checks(
                self, request, *args, **kwargs
            ) -> (bool, str):
                """Could add in additional steps for certificates, APIGateway Authorizers etc"""
                return False, "Some error message raised in subclass"

        obj = SubClassedView()

        res = obj.connect(request)

        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockWebSocketSession.objects.create.call_count)
        MockHttpResponseBadRequest.assert_called_with(
            "Some error message raised in subclass"
        )
        self.assertEqual(0, MockJsonResponse.call_count)

    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__with_missing_headers(
        self, MockJsonResponse, MockHttpResponseBadRequest
    ):
        """Should call the missing_headers method, returning it's result"""
        user = MagicMock(is_authenticated=True)
        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Origin="example.com",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.example.com",
        )
        request.user = user
        obj = views.WebSocketView()

        res = obj.dispatch(request)

        MockHttpResponseBadRequest.assert_called_with("Invalid request headers")
        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockJsonResponse.call_count)

    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__allowed_api_gateway_fails(
        self, MockJsonResponse, MockHttpResponseBadRequest
    ):
        """When _allowed_apigateway returns False the missing_headers method should be called"""
        user = MagicMock(is_authenticated=True)

        class SubClassedView(views.WebSocketView):
            def _allowed_apigateway(self, request, *args, **kwargs) -> bool:
                return False

            def missing_headers(self, request, *args, **kwargs):
                msg = "Got into missing headers"
                return self._return_bad_request(msg)

        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
            HTTP_Cookie="some-cookie",
            HTTP_Origin="example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
            HTTP_HOST="www.example.com",
            HTTP_ORIGIN="https://www.example.com",
        )
        request.user = user
        obj = SubClassedView()

        res = obj.dispatch(request)

        MockHttpResponseBadRequest.assert_called_with("Got into missing headers")

        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockJsonResponse.call_count)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch(
        "django_aws_api_gateway_websockets.views.WebSocketView.http_method_not_allowed"
    )
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__when_http_method_is_not_allowed(
        self,
        MockJsonResponse,
        mocked_http_method_not_allowed,
        mocked__allowed_apigateway,
    ):
        """When a HTTP method is used that is not allowed, the http_method_not_allowed method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True

        class SubClassedView(views.WebSocketView):
            http_method_names = ["get"]

        request = self.factory.post(
            "?channel=my-channel",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        obj = SubClassedView()

        res = obj.dispatch(request)

        mocked_http_method_not_allowed.assert_called_with(request)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(res, mocked_http_method_not_allowed.return_value, res.content)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.connect")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__route_is_connect(
        self, MockJsonResponse, mocked_connect, mocked__allowed_apigateway
    ):
        """When the route is connect and the headers, apigateway and method all pass checks the connect method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True

        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="AmazonAPIGateway_APIGateway-1",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        res = views.WebSocketView.as_view()(request, route="connect")

        mocked_connect.assert_called_with(request, route="connect")
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(res, mocked_connect.return_value, res)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._expected_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.disconnect")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__route_is_disconnect__when_useragent_is_expected(
        self,
        MockJsonResponse,
        mocked_disconnect,
        mocked__add_user_to_request,
        mocked__expected_useragent,
        mocked__allowed_apigateway,
    ):
        """When the route is connect and the headers, apigateway and method all pass checks the connect method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True
        mocked__expected_useragent.return_value = True
        mocked__add_user_to_request.return_value = True

        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        res = views.WebSocketView.as_view()(request, route="disconnect")

        mocked_disconnect.assert_called_with(request, route="disconnect")
        mocked__expected_useragent.assert_called_with(request, route="disconnect")
        mocked__add_user_to_request.assert_called_with(request)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(res, mocked_disconnect.return_value)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._expected_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.invalid_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.disconnect")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__route_is_disconnect__when_useragent_is_not_expected(
        self,
        MockJsonResponse,
        mocked_disconnect,
        mock_invalid_useragent,
        mocked__add_user_to_request,
        mocked__expected_useragent,
        mocked__allowed_apigateway,
    ):
        """When the route is connect and the headers, apigateway and method all pass checks the connect method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True
        mocked__expected_useragent.return_value = False

        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        res = views.WebSocketView.as_view()(request, route="disconnect")

        mock_invalid_useragent.assert_called_with(request, route="disconnect")

        mocked__expected_useragent.assert_called_with(request, route="disconnect")
        self.assertEqual(0, mocked_disconnect.call_count)
        self.assertEqual(0, mocked__add_user_to_request.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(res, mock_invalid_useragent.return_value)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._expected_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.invalid_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.disconnect")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__route_is_custom__useragent_is_expected(
        self,
        MockJsonResponse,
        mocked__load_session,
        mocked_disconnect,
        mock_invalid_useragent,
        mocked__add_user_to_request,
        mocked__expected_useragent,
        mocked__allowed_apigateway,
    ):
        """When the route is a custom one your method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True
        mocked__expected_useragent.return_value = True

        class SubClassedView(views.WebSocketView):
            def chat(self, request, *args, **kwargs):
                return "This is the chat method"

        request = self.factory.post(
            "",
            data=json.dumps({"action": "chat"}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        res = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(res, "This is the chat method")
        mocked__expected_useragent.assert_called_with(request, route="chat")
        mocked__add_user_to_request.assert_called_with(request)
        mocked__load_session.assert_called_with(request)
        self.assertEqual(0, mocked_disconnect.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(0, mock_invalid_useragent.call_count)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._expected_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.invalid_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.disconnect")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__route_is_custom__but_useragent_is_unexpected(
        self,
        MockJsonResponse,
        mocked__load_session,
        mocked_disconnect,
        mock_invalid_useragent,
        mocked__add_user_to_request,
        mocked__expected_useragent,
        mocked__allowed_apigateway,
    ):
        """When the route is a custom one your method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True
        mocked__expected_useragent.return_value = False

        class SubClassedView(views.WebSocketView):
            def chat(self, request, *args, **kwargs):
                return "This is the chat method"

        request = self.factory.post(
            "",
            data=json.dumps({"action": "chat"}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        res = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(res, mock_invalid_useragent.return_value)

        mocked__load_session.assert_called_with(request)
        mocked__expected_useragent.assert_called_with(request, route="chat")
        mock_invalid_useragent.assert_called_with(request, route="chat")
        self.assertEqual(0, mocked_disconnect.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(0, mocked__add_user_to_request.call_count)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._allowed_apigateway")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._expected_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.invalid_useragent")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView.disconnect")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch(
        "django_aws_api_gateway_websockets.views.WebSocketView.handler_selection_key_missing"
    )
    @patch(
        "django_aws_api_gateway_websockets.views.WebSocketView.route_selection_key_missing"
    )
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__handler_selection_key_missing(
        self,
        MockJsonResponse,
        mocked_route_selection_key_missing,
        mocked_handler_selection_key_missing,
        mocked__load_session,
        mocked_disconnect,
        mock_invalid_useragent,
        mocked__add_user_to_request,
        mocked__expected_useragent,
        mocked__allowed_apigateway,
    ):
        """When the route is a custom one your method should be invoked"""
        user = MagicMock(is_authenticated=True)
        mocked__allowed_apigateway.return_value = True
        mocked__expected_useragent.return_value = False

        class SubClassedView(views.WebSocketView):
            def chat(self, request, *args, **kwargs):
                return "This is the chat method"

        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_Forwarded_For="123.123.123.123",
            HTTP_X_Forwarded_Proto="https",
            HTTP_Content_Length=123,
            HTTP_Connectionid="1234",
            HTTP_User_Agent="Mozilla/5.0",
            HTTP_X_Amzn_Apigateway_Api_Id="APIGateway-1",
            HTTP_Connection="",
            HTTP_X_Amzn_Trace_Id="123456787654",
            HTTP_X_Forwarded_Port="443",
            HTTP_X_Real_Ip="172.0.0.1",
            HTTP_Cookie="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_Sec_Websocket_Extensions="some-value",
            HTTP_Sec_Websocket_Key="some-key",
            HTTP_Sec_Websocket_Version="1.2.3",
        )
        request.user = user
        res = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(res, mocked_handler_selection_key_missing.return_value)

        mocked_handler_selection_key_missing.assert_called_with(request, route="chat")

        self.assertEqual(0, mocked__load_session.call_count)
        self.assertEqual(0, mocked__expected_useragent.call_count)
        self.assertEqual(0, mock_invalid_useragent.call_count)
        self.assertEqual(0, mocked_disconnect.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(0, mocked__add_user_to_request.call_count)


class WebSocketViewRemainingSimpleTestCase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_route_selection_key_missing_returns_deprecated_bad_request(self):
        request = self.factory.post("/")

        view = views.WebSocketView(debug=True)

        with self.assertWarns(DeprecationWarning):
            response = view.route_selection_key_missing(request)

        self.assertEqual(400, response.status_code)
        self.assertEqual(
            b"route_select_key action missing from request body.",
            response.content,
        )

    def test_handler_selection_key_missing_returns_generic_bad_request(self):
        request = self.factory.post("/")

        view = views.WebSocketView(debug=True)

        response = view.handler_selection_key_missing(request)

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Invalid request format (1)", response.content)

    def test_invalid_useragent_returns_bad_request(self):
        request = self.factory.post(
            "/",
            HTTP_USER_AGENT="UnexpectedUserAgent",
        )

        view = views.WebSocketView(debug=True)
        view.aws_api_gateway_id = "API123"

        response = view.invalid_useragent(request)

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Unexpected Useragent", response.content)

    def test_default_raises_not_implemented_error(self):
        request = self.factory.post("/")

        view = views.WebSocketView()

        with self.assertRaises(NotImplementedError):
            view.default(request)

    def test_has_any_permission_returns_true_when_no_permissions_required(self):
        request = self.factory.post("/")
        request.user = MagicMock()

        view = views.WebSocketView()

        self.assertTrue(view.has_any_permission(request))

    def test_has_any_permission_checks_required_permissions(self):
        request = self.factory.post("/")
        request.user = MagicMock()
        request.user.has_perms.side_effect = [False, True]

        view = views.WebSocketView()
        view.permissions_required = ["app.first_perm", "app.second_perm"]

        self.assertTrue(view.has_any_permission(request))
        request.user.has_perms.assert_any_call(["app.first_perm"])
        request.user.has_perms.assert_any_call(["app.second_perm"])

    def test_has_all_permission_returns_true_when_no_permissions_required(self):
        request = self.factory.post("/")
        request.user = MagicMock()

        view = views.WebSocketView()

        self.assertTrue(view.has_all_permission(request))

    def test_has_all_permission_checks_required_permissions(self):
        request = self.factory.post("/")
        request.user = MagicMock()
        request.user.has_perms.side_effect = [True, False]

        view = views.WebSocketView()
        view.all_permissions_required = ["app.first_perm", "app.second_perm"]

        self.assertFalse(view.has_all_permission(request))
        request.user.has_perms.assert_any_call(["app.first_perm"])
        request.user.has_perms.assert_any_call(["app.second_perm"])


class WebSocketViewRemainingBranchTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="view-branch-user",
            password="password",
        )
        self.api_gateway = ApiGateway.objects.create(
            api_name="Branch Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
            default_channel_name="default-channel",
        )

    def _request(self, route="chat", body=None, query=None):
        request = self.factory.post(
            "/",
            data=json.dumps(body if body is not None else {}),
            content_type="application/json",
            QUERY_STRING=query or "",
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = self.user
        request.session = MagicMock(session_key="session-key")
        return request

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_uses_handler_selection_key(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            USE_WS_TOKEN = False

            def chat(self, request, *args, **kwargs):
                return JsonResponse({"handler": "chat"})

        request = self._request(body={"handler": "chat"})

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"handler": "chat"}, json.loads(response.content))
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_falls_back_to_default_for_disallowed_handler(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            USE_WS_TOKEN = False

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

            def chat(self, request, *args, **kwargs):
                return JsonResponse({"handler": "chat"})

        request = self._request(body={"handler": "_private"})

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"handler": "default"}, json.loads(response.content))
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_returns_empty_json_when_handler_returns_none(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            USE_WS_TOKEN = False

            def default(self, request, *args, **kwargs):
                return None

        request = self._request(body={"handler": "default"})

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({}, json.loads(response.content))
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_denies_when_all_permissions_required_fail(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            USE_WS_TOKEN = False
            all_permissions_required = ["app.can_chat"]

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

        request = self._request(body={"handler": "default"})
        request.user.has_perms = MagicMock(return_value=False)

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(403, response.status_code)
        self.assertEqual(b"Permission Denied", response.content)
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_denies_when_any_permissions_required_fail(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            USE_WS_TOKEN = False
            permissions_required = ["app.can_chat"]

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

        request = self._request(body={"handler": "default"})
        request.user.has_perms = MagicMock(return_value=False)

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(403, response.status_code)
        self.assertEqual(b"Permission Denied", response.content)
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    @patch(
        "django_aws_api_gateway_websockets.views.ConnectionRateLimit.check_rate_limit"
    )
    def test_connect_returns_bad_request_when_rate_limited(
        self,
        mocked_check_rate_limit,
        mocked_record_attempt,
    ):
        mocked_check_rate_limit.return_value = (False, 20)
        request = self._request(route="connect")

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Too many connection attempts", response.content)
        mocked_record_attempt.assert_called_with(
            "123.123.123.123",
            self.user,
            successful=False,
        )

    def test_connect_returns_bad_request_when_connection_headers_missing(self):
        request = self.factory.post(
            "/",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_CONNECTIONID="CONNECTION-123",
        )
        request.user = self.user
        request.session = MagicMock(session_key="session-key")

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = False

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertIn(b"Missing", response.content)

    @override_settings(ALLOWED_HOSTS=["allowed.example.com"])
    def test_connect_returns_bad_request_when_host_is_not_allowed(self):
        request = self._request(route="connect")
        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = False

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertIn(b"Host is not in AllowedHosts", response.content)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_returns_bad_request_when_host_is_not_in_origin(self):
        request = self._request(route="connect")
        request.META["HTTP_ORIGIN"] = "https://other.example.com"

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = False

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Host is not in Origin", response.content)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_returns_bad_request_when_token_enabled_and_session_missing(self):
        request = self._request(route="connect")
        request.session = MagicMock(session_key=None)

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = True

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Invalid session", response.content)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch(
        "django_aws_api_gateway_websockets.views.WebSocketToken.validate_and_consume"
    )
    def test_connect_returns_bad_request_when_token_is_invalid(
        self,
        mocked_validate_and_consume,
    ):
        mocked_validate_and_consume.return_value = None
        request = self._request(route="connect", query="ws_token=bad-token")

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = True

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Invalid or expired token", response.content)
        mocked_validate_and_consume.assert_called_with(
            token_value="bad-token",
            session_key="session-key",
            max_age_seconds=60,
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    def test_connect_returns_bad_request_when_additional_checks_fail(
        self,
        mocked_record_attempt,
    ):
        request = self._request(route="connect")

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = False
        view._additional_connection_checks = MagicMock(
            return_value=(False, "Additional check failed")
        )

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Additional check failed", response.content)
        mocked_record_attempt.assert_called_with(
            "123.123.123.123",
            self.user,
            successful=False,
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    def test_connect_creates_session_when_successful_without_token(
        self,
        mocked_record_attempt,
    ):
        request = self._request(route="connect", query="channel=test-channel")

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = False

        response = view.connect(request, route="connect")

        self.assertEqual(200, response.status_code)
        self.assertTrue(
            WebSocketSession.objects.filter(
                connection_id="CONNECTION-123",
                channel_name="test-channel",
                user=self.user,
                api_gateway=self.api_gateway,
            ).exists()
        )
        mocked_record_attempt.assert_called_with(
            "123.123.123.123",
            self.user,
            successful=True,
        )

    def test_disconnect_marks_session_disconnected(self):
        WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name="test-channel",
            connected=True,
            user=self.user,
            api_gateway=self.api_gateway,
        )
        request = self._request(route="disconnect")

        view = views.WebSocketView(api_gateway=self.api_gateway)
        response = view.disconnect(request, route="disconnect")

        session = WebSocketSession.objects.get(connection_id="CONNECTION-123")
        self.assertIsNone(response)
        self.assertFalse(session.connected)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_route_selection_key_present_but_route_handler_not_allowed(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            ALLOWED_HANDLERS = {"default"}

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

            def blocked_route(self, request, *args, **kwargs):
                return JsonResponse({"handler": "blocked_route"})

        request = self._request(
            body={
                "handler": "not_allowed_handler",
                "action": "blocked_route",
            }
        )

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"handler": "default"}, json.loads(response.content))
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession.objects.create")
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    @patch(
        "django_aws_api_gateway_websockets.views.ConnectionRateLimit.check_rate_limit"
    )
    @patch(
        "django_aws_api_gateway_websockets.views.WebSocketToken.validate_and_consume"
    )
    def test_connect_valid_token_branch_with_plain_truthy_user_mock(
        self,
        mocked_validate_and_consume,
        mocked_check_rate_limit,
        mocked_record_attempt,
        mocked_session_create,
    ):
        validated_user = MagicMock()
        validated_user.is_authenticated = True
        mocked_validate_and_consume.return_value = validated_user
        mocked_check_rate_limit.return_value = (True, 0)

        request = self._request(
            route="connect",
            query="ws_token=valid-token&channel=token-channel",
        )

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = True

        response = view.connect(request, route="connect")

        self.assertEqual(200, response.status_code)
        mocked_validate_and_consume.assert_called_once_with(
            token_value="valid-token",
            session_key="session-key",
            max_age_seconds=60,
        )
        mocked_session_create.assert_called_once_with(
            connection_id="CONNECTION-123",
            channel_name="token-channel",
            user=validated_user,
            api_gateway=self.api_gateway,
            session_key_hash=ANY,
            auth_hash=ANY,
        )
        mocked_record_attempt.assert_called_with(
            "123.123.123.123",
            self.user,
            successful=True,
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    @patch(
        "django_aws_api_gateway_websockets.views.ConnectionRateLimit.check_rate_limit"
    )
    def test_connect_success_with_rate_limiting_disabled_skips_success_record_attempt(
        self,
        mocked_check_rate_limit,
        mocked_record_attempt,
    ):
        request = self._request(
            route="connect",
            query="channel=rate-limit-disabled-channel",
        )
        request.META["HTTP_CONNECTIONID"] = "RATE-LIMIT-DISABLED-CONNECTION-123"

        view = views.WebSocketView(api_gateway=self.api_gateway, debug=True)
        view.USE_WS_TOKEN = False
        view.RATE_LIMIT_ENABLED = False

        response = view.connect(request, route="connect")

        self.assertEqual(200, response.status_code)
        self.assertEqual({}, json.loads(response.content))

        self.assertTrue(
            WebSocketSession.objects.filter(
                connection_id="RATE-LIMIT-DISABLED-CONNECTION-123",
                channel_name="rate-limit-disabled-channel",
                user=self.user,
                api_gateway=self.api_gateway,
            ).exists()
        )
        mocked_check_rate_limit.assert_not_called()
        mocked_record_attempt.assert_not_called()


class WebSocketViewConsolidatedFinalCoverageTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="consolidated-coverage-user",
            password="password",
        )
        self.api_gateway = ApiGateway.objects.create(
            api_name="Consolidated Coverage Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
            default_channel_name="default-channel",
        )

    def _request(self, body=None, query_string=""):
        request = self.factory.post(
            "/",
            data=json.dumps(body if body is not None else {}),
            content_type="application/json",
            QUERY_STRING=query_string,
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONSOLIDATED-CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = self.user
        request.session = MagicMock(session_key="session-key")
        return request

    def test_missing_headers_debug_true_logs_expected_headers(self):
        request = self.factory.post("/")
        view = views.WebSocketView(debug=True)

        response = view.missing_headers(request)

        self.assertEqual(400, response.status_code)
        self.assertEqual(b"Invalid request headers", response.content)
        self.assertEqual(1, len(view.debug_log))
        self.assertIn("Expected", view.debug_log[0])
        self.assertIn("Received", view.debug_log[0])

    def test_add_user_to_request_skips_invalid_connection_id(self):
        request = self.factory.post(
            "/",
            HTTP_CONNECTIONID="invalid connection id",
        )
        request.user = self.user

        view = views.WebSocketView(debug=True)

        view._add_user_to_request(request)

        self.assertEqual(self.user, request.user)
        self.assertEqual([], view.debug_log)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_all_permissions_passes_and_calls_handler(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            all_permissions_required = ["app.can_chat"]

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

        request = self._request(body={"handler": "default"})
        request.user.has_perms = MagicMock(return_value=True)

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"handler": "default"}, json.loads(response.content))
        request.user.has_perms.assert_called_once_with(["app.can_chat"])
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_any_permissions_passes_and_calls_handler(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            permissions_required = ["app.can_chat"]

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

        request = self._request(body={"handler": "default"})
        request.user.has_perms = MagicMock(return_value=True)

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"handler": "default"}, json.loads(response.content))
        request.user.has_perms.assert_called_once_with(["app.can_chat"])
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @patch("django_aws_api_gateway_websockets.views.WebSocketView._load_session")
    @patch("django_aws_api_gateway_websockets.views.WebSocketView._add_user_to_request")
    def test_dispatch_all_permissions_take_precedence_over_any_permissions(
        self,
        mocked_add_user_to_request,
        mocked_load_session,
    ):
        class SubClassedView(views.WebSocketView):
            all_permissions_required = ["app.all_perm"]
            permissions_required = ["app.any_perm"]

            def default(self, request, *args, **kwargs):
                return JsonResponse({"handler": "default"})

        request = self._request(body={"handler": "default"})
        request.user.has_perms = MagicMock(return_value=True)

        response = SubClassedView.as_view()(request, route="chat")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"handler": "default"}, json.loads(response.content))
        request.user.has_perms.assert_called_once_with(["app.all_perm"])
        mocked_load_session.assert_called_with(request)
        mocked_add_user_to_request.assert_called_with(request)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch(
        "django_aws_api_gateway_websockets.views.WebSocketToken.validate_and_consume"
    )
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    @patch(
        "django_aws_api_gateway_websockets.views.ConnectionRateLimit.check_rate_limit"
    )
    def test_connect_success_with_valid_token_sets_request_user(
        self,
        mocked_check_rate_limit,
        mocked_record_attempt,
        mocked_validate_and_consume,
    ):
        token_user = User.objects.create_user(
            username="consolidated-token-user",
            password="password",
        )
        mocked_check_rate_limit.return_value = (True, 0)
        mocked_validate_and_consume.return_value = token_user

        request = self._request(
            query_string="ws_token=valid-token&channel=token-channel"
        )

        view = views.WebSocketView(api_gateway=self.api_gateway)
        view.USE_WS_TOKEN = True

        response = view.connect(request, route="connect")

        self.assertEqual(200, response.status_code)
        self.assertTrue(
            WebSocketSession.objects.filter(
                connection_id="CONSOLIDATED-CONNECTION-123",
                channel_name="token-channel",
                user=token_user,
                api_gateway=self.api_gateway,
            ).exists()
        )
        mocked_validate_and_consume.assert_called_with(
            token_value="valid-token",
            session_key="session-key",
            max_age_seconds=60,
        )
        mocked_record_attempt.assert_called_with(
            "123.123.123.123",
            self.user,
            successful=True,
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit.record_attempt")
    @patch(
        "django_aws_api_gateway_websockets.views.ConnectionRateLimit.check_rate_limit"
    )
    def test_connect_success_when_rate_limit_disabled_does_not_check_or_record_attempt(
        self,
        mocked_check_rate_limit,
        mocked_record_attempt,
    ):
        request = self._request(query_string="channel=no-rate-limit-channel")

        view = views.WebSocketView(api_gateway=self.api_gateway)
        view.USE_WS_TOKEN = False
        view.RATE_LIMIT_ENABLED = False

        response = view.connect(request, route="connect")

        self.assertEqual(200, response.status_code)
        self.assertTrue(
            WebSocketSession.objects.filter(
                connection_id="CONSOLIDATED-CONNECTION-123",
                channel_name="no-rate-limit-channel",
                user=self.user,
                api_gateway=self.api_gateway,
            ).exists()
        )
        mocked_check_rate_limit.assert_not_called()
        mocked_record_attempt.assert_not_called()


class WebSocketViewSessionTrustTestCase(TestCase):
    """The ``Connectionid`` header is only trusted for a live session on this gateway."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="trust-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="Trust Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )
        self.other_gateway = ApiGateway.objects.create(
            api_name="Other Trust Gateway",
            api_description="A second api gateway",
            target_base_endpoint="http://www.example2.com/",
            api_id="APIGateway-2",
        )

    def _request(self, connection_id="CONNECTION-123", body=None, query=None):
        request = self.factory.post(
            "/",
            data=json.dumps(body if body is not None else {}),
            content_type="application/json",
            QUERY_STRING=query or "",
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID=connection_id,
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = AnonymousUser()
        request.session = MagicMock(session_key="session-key")
        return request

    def _session(self, connected=True, api_gateway=None, **kwargs):
        return WebSocketSession.objects.create(
            connection_id=kwargs.pop("connection_id", "CONNECTION-123"),
            channel_name="test-channel",
            connected=connected,
            api_gateway=api_gateway or self.api_gateway,
            **kwargs,
        )

    def _view(self, api_gateway=None, **kwargs):
        view = views.WebSocketView(**kwargs)
        view.api_gateway = api_gateway or self.api_gateway
        return view

    # connect: the ID must be well formed before a session is stored

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_rejects_malformed_connection_id(self):
        for connection_id in ("bad id<script>", "a" * 129, "has/slash"):
            with self.subTest(connection_id=connection_id):
                view = self._view()
                view.USE_WS_TOKEN = False
                view.RATE_LIMIT_ENABLED = False

                response = view.connect(
                    self._request(connection_id=connection_id), route="connect"
                )

                self.assertEqual(400, response.status_code)
                self.assertFalse(WebSocketSession.objects.exists())

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_accepts_well_formed_connection_id(self):
        view = self._view()
        view.USE_WS_TOKEN = False
        view.RATE_LIMIT_ENABLED = False

        response = view.connect(
            self._request(connection_id="abcABC123_=-"), route="connect"
        )

        self.assertEqual(200, response.status_code)
        self.assertTrue(
            WebSocketSession.objects.filter(connection_id="abcABC123_=-").exists()
        )

    # _load_session

    def test_load_session_finds_connected_session_on_this_gateway(self):
        session = self._session()

        view = self._view()

        self.assertTrue(view._load_session(self._request()))
        self.assertEqual(session, view.websocket_session)

    def test_load_session_ignores_a_disconnected_session(self):
        self._session(connected=False)

        view = self._view()

        self.assertFalse(view._load_session(self._request()))
        self.assertIsNone(view.websocket_session)

    def test_load_session_ignores_a_session_from_another_gateway(self):
        self._session(api_gateway=self.other_gateway)

        view = self._view()

        self.assertFalse(view._load_session(self._request()))

    def test_load_session_returns_false_for_an_unknown_connection_id(self):
        self.assertFalse(self._view()._load_session(self._request()))

    # _add_user_to_request

    def test_add_user_to_request_sets_user_for_connected_session(self):
        start = self._session(user=self.user).request_count
        request = self._request()

        self._view()._add_user_to_request(request)

        self.assertEqual(self.user, request.user)
        self.assertEqual(start + 1, WebSocketSession.objects.get().request_count)

    def test_add_user_to_request_ignores_a_disconnected_session(self):
        """A closed session must not act as a credential for its user."""
        start = self._session(connected=False, user=self.user).request_count
        request = self._request()

        self._view()._add_user_to_request(request)

        self.assertTrue(request.user.is_anonymous)
        self.assertEqual(start, WebSocketSession.objects.get().request_count)

    def test_add_user_to_request_ignores_a_session_from_another_gateway(self):
        start = self._session(
            api_gateway=self.other_gateway, user=self.user
        ).request_count
        request = self._request()

        self._view()._add_user_to_request(request)

        self.assertTrue(request.user.is_anonymous)
        self.assertEqual(start, WebSocketSession.objects.get().request_count)

    # dispatch

    def test_dispatch_rejects_a_message_for_a_disconnected_session(self):
        self._session(connected=False, user=self.user)
        called = []

        class ChatView(views.WebSocketView):
            ALLOWED_HANDLERS = {"chat"}

            def chat(self, request, *args, **kwargs):
                called.append(request.user)
                return JsonResponse({"ok": True})

        request = self._request(body={"action": "chat"})
        view = ChatView()
        view.setup(request, route="default")

        response = view.dispatch(request, route="default")

        self.assertEqual(400, response.status_code)
        self.assertEqual([], called)

    def test_dispatch_runs_handler_for_a_connected_session(self):
        self._session(user=self.user)
        called = []

        class ChatView(views.WebSocketView):
            ALLOWED_HANDLERS = {"chat"}

            def chat(self, request, *args, **kwargs):
                called.append(request.user)
                return JsonResponse({"ok": True})

        request = self._request(body={"action": "chat"})
        view = ChatView()
        view.setup(request, route="default")

        response = view.dispatch(request, route="default")

        self.assertEqual(200, response.status_code)
        self.assertEqual([self.user], called)


class WebSocketViewBodyParsingSimpleTestCase(SimpleTestCase):
    """A malformed request body is treated as empty rather than raising."""

    def setUp(self):
        self.factory = RequestFactory()

    def _body_after_setup(self, raw: bytes):
        request = self.factory.post("/", data=raw, content_type="application/json")
        view = views.WebSocketView(debug=True)
        view.setup(request)
        return view.body

    def test_setup_coerces_non_dict_json_to_empty_dict(self):
        for raw in (b"[1, 2]", b'"action"', b"5", b"null", b"true"):
            with self.subTest(raw=raw):
                self.assertEqual({}, self._body_after_setup(raw))

    def test_setup_keeps_a_json_object(self):
        self.assertEqual({"a": 1}, self._body_after_setup(b'{"a": 1}'))

    def test_setup_uses_empty_dict_for_invalid_utf8(self):
        self.assertEqual({}, self._body_after_setup(b'{"a": "\xff\xfe"}'))

    def test_setup_uses_empty_dict_for_excessively_nested_json(self):
        self.assertEqual({}, self._body_after_setup(b"[" * 50000))

    def test_send_exception_mail_keeps_its_original_default(self):
        """Backwards compatible: handler exceptions are emailed unless a view opts out."""
        self.assertTrue(views.WebSocketView.SEND_EXCEPTION_MAIL)


class WebSocketViewClientInputTestCase(TestCase):
    """Bad client input gets a 4xx response, not an exception and an admin email."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="input-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="Input Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )

    def _request(self, body=None, query=None, raw=None):
        request = self.factory.post(
            "/",
            data=(
                raw if raw is not None else json.dumps(body if body is not None else {})
            ),
            content_type="application/json",
            QUERY_STRING=query or "",
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = self.user
        request.session = MagicMock(session_key="session-key")
        return request

    def _session(self, **kwargs):
        return WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name=kwargs.pop("channel_name", "test-channel"),
            connected=kwargs.pop("connected", True),
            api_gateway=self.api_gateway,
            user=self.user,
            **kwargs,
        )

    # dispatch with a non-object body

    def test_dispatch_with_non_object_body_returns_400(self):
        self._session()
        for raw in ("[1, 2]", '"action"', "5"):
            with self.subTest(raw=raw):
                request = self._request(raw=raw)
                view = views.WebSocketView()
                view.setup(request, route="default")

                response = view.dispatch(request, route="default")

                self.assertEqual(400, response.status_code)

    # login still holds

    def _opened_session(self, **kwargs):
        return self._session(
            auth_hash=hash_user_auth(self.user),
            session_key_hash=hash_session_key("session-key"),
            **kwargs,
        )

    def test_a_message_from_an_active_user_sets_the_user(self):
        self._opened_session()
        request = self._request()
        request.user = AnonymousUser()
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertTrue(view._add_user_to_request(request))

        self.assertEqual(self.user, request.user)

    def test_a_message_for_a_deactivated_user_closes_the_session(self):
        session = self._opened_session()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        request = self._request()
        request.user = AnonymousUser()
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertFalse(view._add_user_to_request(request))

        session.refresh_from_db()
        self.assertFalse(session.connected)
        self.assertIsInstance(request.user, AnonymousUser)

    def test_a_message_after_a_password_change_closes_the_session(self):
        session = self._opened_session()
        self.user.set_password("a-new-password")
        self.user.save()
        request = self._request()
        request.user = AnonymousUser()
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertFalse(view._add_user_to_request(request))

        session.refresh_from_db()
        self.assertFalse(session.connected)

    def test_a_session_opened_before_the_hashes_existed_is_kept_for_an_active_user(
        self,
    ):
        session = self._session()
        request = self._request()
        request.user = AnonymousUser()
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertTrue(view._add_user_to_request(request))

        session.refresh_from_db()
        self.assertTrue(session.connected)

    def test_a_session_with_no_user_is_not_checked(self):
        session = self._session()
        WebSocketSession.objects.filter(pk=session.pk).update(user=None)
        view = views.WebSocketView(api_gateway=self.api_gateway)

        self.assertTrue(view._add_user_to_request(self._request()))

    def _dispatch_chat(self):
        """Send a ``chat`` message through ``dispatch``, returning the response and whether the handler ran"""

        class ChatView(views.WebSocketView):
            ALLOWED_HANDLERS = {"chat"}
            ran = False

            def chat(self, request, *args, **kwargs):
                type(self).ran = True
                return JsonResponse({"ok": True})

        request = self._request(body={"action": "chat"})
        view = ChatView()
        view.setup(request, route="chat")
        response = view.dispatch(request, route="chat")
        return response, ChatView.ran

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_dispatch_runs_the_handler_for_a_message_from_an_active_user(self):
        self._opened_session()

        response, handled = self._dispatch_chat()

        self.assertEqual(200, response.status_code)
        self.assertTrue(handled)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_message_costs_three_queries(self):
        """The gateway, the session with its user, and the request counter"""
        self._opened_session()

        with self.assertNumQueries(3):
            response, handled = self._dispatch_chat()

        self.assertEqual(200, response.status_code)
        self.assertTrue(handled)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_message_counts_one_request(self):
        session = self._opened_session()
        before = session.request_count

        self._dispatch_chat()

        session.refresh_from_db()
        self.assertEqual(before + 1, session.request_count)

    def test_two_views_holding_the_same_session_both_count(self):
        """The counter is one UPDATE, so neither message overwrites the other's count"""
        session = self._opened_session()
        before = session.request_count
        views_ = []
        for _ in range(2):
            view = views.WebSocketView(api_gateway=self.api_gateway)
            request = self._request()
            view._load_session(request)
            views_.append((view, request))

        for view, request in views_:
            self.assertTrue(view._add_user_to_request(request))

        session.refresh_from_db()
        self.assertEqual(before + 2, session.request_count)

    def test_the_session_is_not_loaded_again_when_dispatch_already_has_it(self):
        self._opened_session()
        request = self._request()
        view = views.WebSocketView(api_gateway=self.api_gateway)
        view._load_session(request)

        with self.assertNumQueries(1):  # the counter only
            view._add_user_to_request(request)

    def test_a_user_who_is_no_longer_active_is_found_without_a_second_query(self):
        session = self._opened_session()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        request = self._request()
        view = views.WebSocketView(api_gateway=self.api_gateway)
        view._load_session(request)

        with self.assertNumQueries(1):  # closing the session only
            self.assertFalse(view._add_user_to_request(request))

        session.refresh_from_db()
        self.assertFalse(session.connected)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_dispatch_answers_a_message_from_a_deactivated_user_with_400(self):
        self._opened_session()
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        response, handled = self._dispatch_chat()

        self.assertEqual(400, response.status_code)
        self.assertFalse(handled)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_stores_the_hashes_that_tie_the_session_to_the_login(self):
        request = self._request(query="channel=test-channel")
        view = views.WebSocketView(api_gateway=self.api_gateway)
        view.USE_WS_TOKEN = False

        response = view.connect(request, route="connect")

        self.assertEqual(200, response.status_code)
        session = WebSocketSession.objects.get(connection_id="CONNECTION-123")
        self.assertEqual(hash_session_key("session-key"), session.session_key_hash)
        self.assertEqual(hash_user_auth(self.user), session.auth_hash)
        self.assertNotIn("session-key", session.session_key_hash)

    def test_logging_out_closes_the_sessions_opened_under_that_login(self):
        mine = self._opened_session()
        other = WebSocketSession.objects.create(
            connection_id="CONNECTION-456",
            user=self.user,
            api_gateway=self.api_gateway,
            session_key_hash=hash_session_key("another-session-key"),
        )
        request = self._request()

        user_logged_out.send(sender=User, request=request, user=self.user)

        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(mine.connected)
        self.assertTrue(other.connected)

    def test_logging_out_without_a_session_key_closes_nothing(self):
        session = self._opened_session()
        request = self._request()
        request.session = MagicMock(session_key=None)

        user_logged_out.send(sender=User, request=request, user=self.user)
        user_logged_out.send(sender=User, request=None, user=None)

        session.refresh_from_db()
        self.assertTrue(session.connected)

    # disconnect

    def test_disconnect_for_unknown_connection_returns_400(self):
        request = self._request()
        view = views.WebSocketView()
        view.api_gateway = self.api_gateway

        response = view.disconnect(request, route="disconnect")

        self.assertEqual(400, response.status_code)

    def test_disconnect_marks_known_session_disconnected(self):
        session = self._session()
        view = views.WebSocketView()
        view.api_gateway = self.api_gateway

        response = view.disconnect(self._request(), route="disconnect")

        session.refresh_from_db()
        self.assertIsNone(response)
        self.assertFalse(session.connected)

    def test_dispatch_disconnect_for_unknown_connection_does_not_raise(self):
        request = self._request()
        view = views.WebSocketView()
        view.setup(request, route="disconnect")

        response = view.dispatch(request, route="disconnect")

        self.assertEqual(400, response.status_code)

    # connect: the channel is validated before the one-time token is spent

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect_with_invalid_channel_returns_400_without_consuming_token(
        self, MockWebSocketToken
    ):
        for channel in ("bad channel", "a" * 192, "semi;colon"):
            with self.subTest(channel=channel):
                request = self._request(query=f"ws_token=abc&channel={channel}")
                view = views.WebSocketView()
                view.api_gateway = self.api_gateway
                view.RATE_LIMIT_ENABLED = False

                response = view.connect(request, route="connect")

                self.assertEqual(400, response.status_code)
                MockWebSocketToken.validate_and_consume.assert_not_called()
                self.assertFalse(WebSocketSession.objects.exists())

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    @patch("django_aws_api_gateway_websockets.views.WebSocketToken")
    def test_connect_with_invalid_channel_records_failed_attempt(
        self, MockWebSocketToken, MockConnectionRateLimit
    ):
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 0)
        request = self._request(query="ws_token=abc&channel=bad channel")
        view = views.WebSocketView()
        view.api_gateway = self.api_gateway

        response = view.connect(request, route="connect")

        self.assertEqual(400, response.status_code)
        MockConnectionRateLimit.record_attempt.assert_called_once_with(
            "123.123.123.123", self.user, successful=False
        )

    # change_channel

    def test_change_channel_rejects_missing_non_string_and_invalid_channels(self):
        for body in (
            {},
            {"channel": 5},
            {"channel": ["a"]},
            {"channel": "bad channel"},
        ):
            with self.subTest(body=body):
                session = self._session(channel_name="old-channel")
                view = views.WebSocketView()
                view.websocket_session = session
                view.body = body

                response = view.change_channel(self._request())

                self.assertEqual(400, response.status_code)
                session.refresh_from_db()
                self.assertEqual("old-channel", session.channel_name)
                session.delete()

    def test_change_channel_length_limit_matches_the_database_column(self):
        session = self._session(channel_name="old-channel")
        view = views.WebSocketView()
        view.websocket_session = session

        view.body = {"channel": "a" * 129}
        self.assertEqual(400, view.change_channel(self._request()).status_code)

        view.body = {"channel": "a" * 128}
        self.assertIsNone(view.change_channel(self._request()))
        session.refresh_from_db()
        self.assertEqual("a" * 128, session.channel_name)

    def test_change_channel_accepts_a_valid_channel(self):
        session = self._session(channel_name="old-channel")
        view = views.WebSocketView()
        view.websocket_session = session
        view.body = {"channel": "new-channel_1"}

        response = view.change_channel(self._request())

        self.assertIsNone(response)
        session.refresh_from_db()
        self.assertEqual("new-channel_1", session.channel_name)

    # exception mail

    def _raising_view(self, **attrs):
        class RaisingView(views.WebSocketView):
            ALLOWED_HANDLERS = {"boom"}

            def boom(self, request, *args, **kwargs):
                raise RuntimeError("boom")

        for name, value in attrs.items():
            setattr(RaisingView, name, value)
        return RaisingView()

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_handler_exception_mails_admins_by_default(self, mocked_mail):
        self._session()
        request = self._request(body={"action": "boom"})
        view = self._raising_view()
        view.setup(request, route="default")

        with (
            self.assertLogs("django_aws_api_gateway_websockets.views", level="ERROR"),
            self.assertRaises(RuntimeError),
        ):
            view.dispatch(request, route="default")

        mocked_mail.assert_called_once()

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_handler_exception_does_not_mail_admins_when_disabled(self, mocked_mail):
        self._session()
        request = self._request(body={"action": "boom"})
        view = self._raising_view(SEND_EXCEPTION_MAIL=False)
        view.setup(request, route="default")

        with (
            self.assertLogs("django_aws_api_gateway_websockets.views", level="ERROR"),
            self.assertRaises(RuntimeError),
        ):
            view.dispatch(request, route="default")

        mocked_mail.assert_not_called()

    def _dispatch_boom(self, view):
        request = self._request(body={"action": "boom"})
        view.setup(request, route="default")
        with (
            self.assertLogs("django_aws_api_gateway_websockets.views", level="ERROR"),
            self.assertRaises(RuntimeError),
        ):
            view.dispatch(request, route="default")

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_a_repeated_exception_mails_admins_once_for_each_interval(
        self, mocked_mail
    ):
        self._session()
        view = self._raising_view()

        with patch("django_aws_api_gateway_websockets.views.time.monotonic") as clock:
            clock.return_value = 1000.0
            self._dispatch_boom(view)
            clock.return_value = 1030.0
            self._dispatch_boom(view)
            self._dispatch_boom(view)
            self.assertEqual(1, mocked_mail.call_count)

            clock.return_value = 1061.0
            self._dispatch_boom(view)

        self.assertEqual(2, mocked_mail.call_count)

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_every_exception_is_still_logged_when_the_mail_is_held_back(
        self, mocked_mail
    ):
        self._session()
        view = self._raising_view()
        request = self._request(body={"action": "boom"})
        view.setup(request, route="default")

        with patch(
            "django_aws_api_gateway_websockets.views.time.monotonic", return_value=5.0
        ):
            for _ in range(3):
                with (
                    self.assertLogs(
                        "django_aws_api_gateway_websockets.views", level="ERROR"
                    ) as logs,
                    self.assertRaises(RuntimeError),
                ):
                    view.dispatch(request, route="default")
                self.assertTrue(logs.records)

        self.assertEqual(1, mocked_mail.call_count)

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_a_different_exception_or_view_gets_its_own_mail(self, mocked_mail):
        self._session()
        with patch(
            "django_aws_api_gateway_websockets.views.time.monotonic", return_value=5.0
        ):
            self._dispatch_boom(self._raising_view())
            self._dispatch_boom(self._raising_view())  # another view class

        self.assertEqual(2, mocked_mail.call_count)

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_an_interval_of_zero_mails_every_time(self, mocked_mail):
        self._session()
        view = self._raising_view(EXCEPTION_MAIL_INTERVAL=0)

        with patch(
            "django_aws_api_gateway_websockets.views.time.monotonic", return_value=5.0
        ):
            self._dispatch_boom(view)
            self._dispatch_boom(view)

        self.assertEqual(2, mocked_mail.call_count)

    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_bad_client_input_does_not_mail_admins_even_by_default(self, mocked_mail):
        """The input handling fixes mean client mistakes no longer raise at all."""
        self._session()
        view = views.WebSocketView()
        request = self._request(raw="[1, 2]")
        view.setup(request, route="default")

        response = view.dispatch(request, route="default")

        self.assertEqual(400, response.status_code)
        mocked_mail.assert_not_called()


class WebSocketViewChannelAuthorisationTestCase(TestCase):
    """``can_join_channel`` and the permission attributes are enforced on connect."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="chan-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="Channel Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )

    def _request(self, query="channel=room-1", user=None):
        request = self.factory.post(
            "/",
            data=json.dumps({}),
            content_type="application/json",
            QUERY_STRING=query,
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = user or self.user
        request.session = MagicMock(session_key="session-key")
        return request

    def _view(self, view_class=views.WebSocketView):
        view = view_class()
        view.api_gateway = self.api_gateway
        view.USE_WS_TOKEN = False
        view.RATE_LIMIT_ENABLED = False
        return view

    def _session(self, channel_name="old-channel"):
        return WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name=channel_name,
            api_gateway=self.api_gateway,
            user=self.user,
        )

    def _recording_view_class(self, allow):
        calls = []

        class RecordingView(views.WebSocketView):
            def can_join_channel(self, request, channel_name):
                calls.append((request.user, channel_name))
                return allow

        RecordingView.calls = calls
        return RecordingView

    # the default hook

    def test_default_can_join_channel_allows_any_channel(self):
        view = views.WebSocketView()

        for channel in ("", "room-1", "tenant_456"):
            with self.subTest(channel=channel):
                self.assertTrue(view.can_join_channel(self._request(), channel))

    # connect

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_is_refused_when_can_join_channel_returns_false(self):
        view_class = self._recording_view_class(allow=False)
        view = self._view(view_class)

        response = view.connect(self._request(), route="connect")

        self.assertEqual(403, response.status_code)
        self.assertFalse(WebSocketSession.objects.exists())
        self.assertEqual([(self.user, "room-1")], view_class.calls)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_creates_the_session_when_can_join_channel_returns_true(self):
        view_class = self._recording_view_class(allow=True)

        response = self._view(view_class).connect(self._request(), route="connect")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            "room-1",
            WebSocketSession.objects.get(connection_id="CONNECTION-123").channel_name,
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_passes_the_gateway_default_channel_to_the_hook(self):
        self.api_gateway.default_channel_name = "lobby"
        self.api_gateway.save()
        view_class = self._recording_view_class(allow=True)

        self._view(view_class).connect(self._request(query=""), route="connect")

        self.assertEqual([(self.user, "lobby")], view_class.calls)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_is_not_checked_by_the_hook_for_an_invalid_channel(self):
        view_class = self._recording_view_class(allow=True)

        response = self._view(view_class).connect(
            self._request(query="channel=bad channel"), route="connect"
        )

        self.assertEqual(400, response.status_code)
        self.assertEqual([], view_class.calls)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.ConnectionRateLimit")
    def test_refused_connect_records_a_failed_attempt(self, MockConnectionRateLimit):
        MockConnectionRateLimit.check_rate_limit.return_value = (True, 0)
        view = self._view(self._recording_view_class(allow=False))
        view.RATE_LIMIT_ENABLED = True

        view.connect(self._request(), route="connect")

        MockConnectionRateLimit.record_attempt.assert_called_once_with(
            "123.123.123.123", self.user, successful=False
        )

    # permissions on connect

    def _grant(self, codename):
        self.user.user_permissions.add(Permission.objects.get(codename=codename))
        return User.objects.get(pk=self.user.pk)  # drop the cached permissions

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_enforces_permissions_required_when_opted_in(self):
        class GuardedView(views.WebSocketView):
            CHECK_PERMISSIONS_ON_CONNECT = True
            permissions_required = ["auth.view_user"]

        denied = self._view(GuardedView).connect(self._request(), route="connect")
        self.assertEqual(403, denied.status_code)
        self.assertFalse(WebSocketSession.objects.exists())

        allowed = self._view(GuardedView).connect(
            self._request(user=self._grant("view_user")), route="connect"
        )
        self.assertEqual(200, allowed.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_enforces_all_permissions_required_when_opted_in(self):
        class GuardedView(views.WebSocketView):
            CHECK_PERMISSIONS_ON_CONNECT = True
            all_permissions_required = ["auth.view_user", "auth.view_group"]

        user = self._grant("view_user")  # only one of the two
        denied = self._view(GuardedView).connect(
            self._request(user=user), route="connect"
        )
        self.assertEqual(403, denied.status_code)

        user = self._grant("view_group")
        allowed = self._view(GuardedView).connect(
            self._request(user=user), route="connect"
        )
        self.assertEqual(200, allowed.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_denies_an_anonymous_user_when_permissions_are_required(self):
        class GuardedView(views.WebSocketView):
            CHECK_PERMISSIONS_ON_CONNECT = True
            permissions_required = ["auth.view_user"]

        response = self._view(GuardedView).connect(
            self._request(user=AnonymousUser()), route="connect"
        )

        self.assertEqual(403, response.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_does_not_check_view_permissions_by_default(self):
        """Backwards compatible: permissions_required has only ever applied to messages."""

        class GuardedView(views.WebSocketView):
            permissions_required = ["auth.view_user"]
            all_permissions_required = ["auth.view_group"]

        self.assertFalse(GuardedView.CHECK_PERMISSIONS_ON_CONNECT)

        response = self._view(GuardedView).connect(self._request(), route="connect")

        self.assertEqual(200, response.status_code)

    # change_channel

    def test_change_channel_is_refused_when_can_join_channel_returns_false(self):
        view_class = self._recording_view_class(allow=False)
        session = self._session()
        view = self._view(view_class)
        view.websocket_session = session
        view.body = {"channel": "tenant_456"}

        response = view.change_channel(self._request())

        self.assertEqual(403, response.status_code)
        session.refresh_from_db()
        self.assertEqual("old-channel", session.channel_name)
        self.assertEqual([(self.user, "tenant_456")], view_class.calls)

    def test_change_channel_moves_the_session_when_can_join_channel_returns_true(self):
        session = self._session()
        view = self._view(self._recording_view_class(allow=True))
        view.websocket_session = session
        view.body = {"channel": "tenant_456"}

        response = view.change_channel(self._request())

        self.assertIsNone(response)
        session.refresh_from_db()
        self.assertEqual("tenant_456", session.channel_name)

    def test_change_channel_does_not_call_the_hook_for_an_invalid_channel(self):
        view_class = self._recording_view_class(allow=True)
        view = self._view(view_class)
        view.websocket_session = self._session()
        view.body = {"channel": "bad channel"}

        response = view.change_channel(self._request())

        self.assertEqual(400, response.status_code)
        self.assertEqual([], view_class.calls)


class WebSocketViewChannelPermissionTestCase(TestCase):
    """The default ``can_join_channel`` enforces ``ChannelPermission`` rows."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="cp-user", password="pw")
        self.staff = User.objects.create_user(
            username="cp-staff", password="pw", is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username="cp-root", password="pw"
        )
        self.api_gateway = ApiGateway.objects.create(
            api_name="CP Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )

    def _request(self, query="channel=room-1", user=None):
        request = self.factory.post(
            "/",
            data=json.dumps({}),
            content_type="application/json",
            QUERY_STRING=query,
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = user or self.user
        request.session = MagicMock(session_key="session-key")
        return request

    def _view(self, view_class=views.WebSocketView):
        view = view_class()
        view.api_gateway = self.api_gateway
        view.USE_WS_TOKEN = False
        view.RATE_LIMIT_ENABLED = False
        return view

    def _channel(self, name, access):
        return ChannelPermission.objects.create(channel_name=name, access=access)

    def _connect(self, view, channel, user):
        return view.connect(
            self._request(query=f"channel={channel}", user=user), route="connect"
        )

    # unlisted channels

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_channel_with_no_row_is_open_by_default(self):
        self.assertTrue(views.WebSocketView.ALLOW_UNLISTED_CHANNELS)

        response = self._connect(self._view(), "anything", AnonymousUser())

        self.assertEqual(200, response.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_unlisted_channels_can_be_refused(self):
        class ClosedView(views.WebSocketView):
            ALLOW_UNLISTED_CHANNELS = False

        self._channel("listed", ChannelPermission.Access.ALLOW_ALL)

        refused = self._connect(self._view(ClosedView), "unlisted", self.user)
        allowed = self._connect(self._view(ClosedView), "listed", self.user)

        self.assertEqual(403, refused.status_code)
        self.assertEqual(200, allowed.status_code)

    # listed channels

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_allow_all_channel_admits_anonymous_users(self):
        self._channel("lobby", ChannelPermission.Access.ALLOW_ALL)

        response = self._connect(self._view(), "lobby", AnonymousUser())

        self.assertEqual(200, response.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_superuser_only_channel(self):
        self._channel("root", ChannelPermission.Access.SUPERUSER_ONLY)

        self.assertEqual(
            403, self._connect(self._view(), "root", self.user).status_code
        )
        self.assertEqual(
            403, self._connect(self._view(), "root", self.staff).status_code
        )
        self.assertFalse(WebSocketSession.objects.exists())
        self.assertEqual(
            200, self._connect(self._view(), "root", self.superuser).status_code
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_staff_only_channel(self):
        self._channel("staff", ChannelPermission.Access.STAFF_ONLY)

        self.assertEqual(
            403, self._connect(self._view(), "staff", self.user).status_code
        )
        self.assertEqual(
            403, self._connect(self._view(), "staff", AnonymousUser()).status_code
        )
        self.assertEqual(
            200, self._connect(self._view(), "staff", self.staff).status_code
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_permissions_channel_uses_the_rules(self):
        channel = self._channel("reports", ChannelPermission.Access.PERMISSIONS)
        rule = ChannelPermissionRule.objects.create(channel_permission=channel)
        rule.permissions.set([Permission.objects.get(codename="view_user")])
        self.user.user_permissions.add(Permission.objects.get(codename="view_user"))
        allowed_user = User.objects.get(pk=self.user.pk)

        self.assertEqual(
            403, self._connect(self._view(), "reports", self.staff).status_code
        )
        self.assertEqual(
            200, self._connect(self._view(), "reports", allowed_user).status_code
        )

    # change_channel uses the same rules

    def test_change_channel_enforces_the_rows(self):
        self._channel("root", ChannelPermission.Access.SUPERUSER_ONLY)
        session = WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name="room-1",
            api_gateway=self.api_gateway,
            user=self.user,
        )
        view = self._view()
        view.websocket_session = session
        view.body = {"channel": "root"}

        response = view.change_channel(self._request(user=self.user))

        self.assertEqual(403, response.status_code)
        session.refresh_from_db()
        self.assertEqual("room-1", session.channel_name)

        self.assertIsNone(view.change_channel(self._request(user=self.superuser)))
        session.refresh_from_db()
        self.assertEqual("root", session.channel_name)

    # extension points

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_get_channel_permission_can_be_overridden(self):
        class TenantView(views.WebSocketView):
            def get_channel_permission(self, channel_name):
                if channel_name.startswith("tenant_"):
                    return ChannelPermission(
                        channel_name=channel_name,
                        access=ChannelPermission.Access.STAFF_ONLY,
                    )
                return None

        self.assertEqual(
            403,
            self._connect(self._view(TenantView), "tenant_1", self.user).status_code,
        )
        self.assertEqual(
            200, self._connect(self._view(TenantView), "room-1", self.user).status_code
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_can_join_channel_override_can_add_to_the_model_checks(self):
        class OwnChannelView(views.WebSocketView):
            def can_join_channel(self, request, channel_name):
                if channel_name.startswith("user_"):
                    return channel_name == f"user_{request.user.pk}"
                return super().can_join_channel(request, channel_name)

        self._channel("root", ChannelPermission.Access.SUPERUSER_ONLY)
        own = f"user_{self.user.pk}"

        def status(channel, user):
            WebSocketSession.objects.all().delete()
            return self._connect(self._view(OwnChannelView), channel, user).status_code

        self.assertEqual(200, status(own, self.user))
        self.assertEqual(403, status(f"user_{self.staff.pk}", self.user))
        self.assertEqual(403, status("root", self.user))  # super() still enforces rows
        self.assertEqual(200, status("room-1", self.user))

    def test_checking_an_unlisted_channel_takes_one_query(self):
        view = self._view()

        with self.assertNumQueries(1):
            view.can_join_channel(self._request(), "room-1")


GATEWAY_SECRET = "s3cr3t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
OLD_GATEWAY_SECRET = "0ld-" + "y" * 40


class WebSocketViewGatewaySecretTestCase(TestCase):
    """With ``WEBSOCKETS["gateway_secret"]`` set, only API Gateway can reach the view."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="secret-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="Secret Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )
        WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name="room-1",
            api_gateway=self.api_gateway,
            user=self.user,
        )

    def _request(self, secret=None, body=None):
        headers = {}
        if secret is not None:
            headers["HTTP_" + GATEWAY_SECRET_HEADER.upper().replace("-", "_")] = secret
        request = self.factory.post(
            "/",
            data=json.dumps(body if body is not None else {"action": "chat"}),
            content_type="application/json",
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
            **headers,
        )
        request.user = AnonymousUser()
        request.session = MagicMock(session_key="session-key")
        return request

    def _dispatch(self, request, route="default"):
        class ChatView(views.WebSocketView):
            ALLOWED_HANDLERS = {"chat"}

            def chat(self, request, *args, **kwargs):
                return JsonResponse({"ok": True})

        view = ChatView()
        view.setup(request, route=route)
        return view.dispatch(request, route=route)

    def test_without_a_configured_secret_no_header_is_needed(self):
        """Backwards compatible: the check is opt-in."""
        with override_settings(WEBSOCKETS={}):
            response = self._dispatch(self._request())

        self.assertEqual(200, response.status_code)

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    def test_a_request_without_the_secret_is_refused(self):
        response = self._dispatch(self._request())

        self.assertEqual(403, response.status_code)

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    def test_a_request_with_the_wrong_secret_is_refused(self):
        for wrong in ("wrong", GATEWAY_SECRET[:-1], GATEWAY_SECRET + "x", ""):
            with self.subTest(secret=wrong):
                response = self._dispatch(self._request(secret=wrong))

                self.assertEqual(403, response.status_code)

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    def test_a_request_with_the_right_secret_is_handled(self):
        response = self._dispatch(self._request(secret=GATEWAY_SECRET))

        self.assertEqual(200, response.status_code)

    @override_settings(
        WEBSOCKETS={"gateway_secret": [GATEWAY_SECRET, OLD_GATEWAY_SECRET]}
    )
    def test_every_configured_secret_is_accepted_to_allow_rotation(self):
        for secret in (GATEWAY_SECRET, OLD_GATEWAY_SECRET):
            with self.subTest(secret=secret):
                response = self._dispatch(self._request(secret=secret))

                self.assertEqual(200, response.status_code)

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    def test_connect_and_disconnect_routes_are_checked_too(self):
        for route in ("connect", "disconnect"):
            with self.subTest(route=route):
                response = self._dispatch(self._request(), route=route)

                self.assertEqual(403, response.status_code)
        self.assertTrue(WebSocketSession.objects.get().connected)
        self.assertEqual(1, WebSocketSession.objects.count())

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    def test_a_forged_request_is_refused_before_any_database_work(self):
        with self.assertNumQueries(0):
            response = self._dispatch(self._request())

        self.assertEqual(403, response.status_code)

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    def test_refusal_does_not_reveal_the_secret(self):
        with self.assertLogs(
            "django_aws_api_gateway_websockets.views", level="WARNING"
        ) as logs:
            response = self._dispatch(self._request(secret="guess"))

        self.assertNotIn(GATEWAY_SECRET, response.content.decode())
        self.assertNotIn(GATEWAY_SECRET, "".join(logs.output))
        self.assertNotIn("guess", "".join(logs.output))

    @override_settings(WEBSOCKETS={"gateway_secret": GATEWAY_SECRET})
    @patch("django_aws_api_gateway_websockets.views.mail_admins")
    def test_a_refused_request_does_not_email_admins(self, mocked_mail):
        self._dispatch(self._request())

        mocked_mail.assert_not_called()


class WebSocketViewUserAgentDispatchTestCase(TestCase):
    """The User-Agent rules as ``dispatch`` applies them to each route."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="ua-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="UA Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="APIGateway-1",
        )
        WebSocketSession.objects.create(
            connection_id="CONNECTION-123",
            channel_name="room-1",
            api_gateway=self.api_gateway,
            user=self.user,
        )

    def _request(self, user_agent, body=None, query=""):
        request = self.factory.post(
            "/",
            data=json.dumps(body if body is not None else {"action": "chat"}),
            content_type="application/json",
            QUERY_STRING=query,
            HTTP_HOST="www.example.com",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_CONTENT_LENGTH="123",
            HTTP_CONNECTIONID="CONNECTION-NEW",
            HTTP_USER_AGENT=user_agent,
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_X_AMZN_TRACE_ID="123456787654",
            HTTP_X_FORWARDED_PORT="443",
            HTTP_X_REAL_IP="172.0.0.1",
            HTTP_COOKIE="some-cookie",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="some-value",
            HTTP_SEC_WEBSOCKET_KEY="some-key",
            HTTP_SEC_WEBSOCKET_VERSION="1.2.3",
        )
        request.user = self.user
        request.session = MagicMock(session_key="session-key")
        return request

    def _dispatch(self, request, route, view_class=None):
        class ChatView(views.WebSocketView):
            ALLOWED_HANDLERS = {"chat"}
            USE_WS_TOKEN = False
            RATE_LIMIT_ENABLED = False

            def chat(self, request, *args, **kwargs):
                return JsonResponse({"ok": True})

        view = (view_class or ChatView)()
        view.setup(request, route=route)
        return view.dispatch(request, route=route)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_with_the_gateway_useragent_creates_the_session(self):
        request = self._request("AmazonAPIGateway_APIGateway-1")

        response = self._dispatch(request, "connect")

        self.assertEqual(200, response.status_code)
        self.assertTrue(
            WebSocketSession.objects.filter(connection_id="CONNECTION-NEW").exists()
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_connect_with_a_real_useragent_is_refused_and_creates_nothing(self):
        request = self._request("Mozilla/5.0")

        response = self._dispatch(request, "connect")

        self.assertEqual(400, response.status_code)
        self.assertFalse(
            WebSocketSession.objects.filter(connection_id="CONNECTION-NEW").exists()
        )

    def test_a_message_with_a_real_useragent_is_handled(self):
        """The case the old code got wrong in the default mode."""
        request = self._request("Mozilla/5.0")
        request.META["HTTP_CONNECTIONID"] = "CONNECTION-123"

        response = self._dispatch(request, "default")

        self.assertEqual(200, response.status_code)

    def test_a_message_with_a_real_useragent_is_handled_when_the_view_is_pinned(self):
        class PinnedView(views.WebSocketView):
            ALLOWED_HANDLERS = {"chat"}
            aws_api_gateway_id = "APIGateway-1"

            def chat(self, request, *args, **kwargs):
                return JsonResponse({"ok": True})

        request = self._request("Mozilla/5.0")
        request.META["HTTP_CONNECTIONID"] = "CONNECTION-123"

        response = self._dispatch(request, "default", view_class=PinnedView)

        self.assertEqual(200, response.status_code)

    def test_disconnect_with_a_real_useragent_is_handled(self):
        request = self._request("Mozilla/5.0")
        request.META["HTTP_CONNECTIONID"] = "CONNECTION-123"

        response = self._dispatch(request, "disconnect")

        self.assertEqual(200, response.status_code)
        self.assertFalse(
            WebSocketSession.objects.get(connection_id="CONNECTION-123").connected
        )

    def test_a_message_without_a_useragent_is_refused_by_the_header_check(self):
        """User-Agent is a required header, so this is a 400 response and not an error."""
        request = self._request("x")
        del request.META["HTTP_USER_AGENT"]
        request.META["HTTP_CONNECTIONID"] = "CONNECTION-123"

        response = self._dispatch(request, "default")

        self.assertEqual(400, response.status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    def test_a_connect_without_a_useragent_is_refused_not_an_error(self):
        request = self._request("x")
        del request.META["HTTP_USER_AGENT"]

        response = self._dispatch(request, "connect")

        self.assertEqual(400, response.status_code)


class WebSocketViewPartialWritesTestCase(TestCase):
    """Handlers write only the fields they change, so they do not undo other requests."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="pw-user", password="pw")
        self.api_gateway = ApiGateway.objects.create(
            api_name="PW Gateway",
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

    def _request(self):
        request = self.factory.post(
            "/",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_CONNECTIONID="CONNECTION-123",
        )
        request.user = self.user
        return request

    def _concurrent_update(self, **fields):
        """Another request changes the row after this one loaded its copy."""
        WebSocketSession.objects.filter(pk=self.session.pk).update(**fields)

    def test_change_channel_does_not_overwrite_a_concurrent_update(self):
        stale = WebSocketSession.objects.get(pk=self.session.pk)
        view = views.WebSocketView()
        view.websocket_session = stale
        view.body = {"channel": "room-2"}
        self._concurrent_update(request_count=99, connected=False)

        view.change_channel(self._request())

        row = WebSocketSession.objects.get(pk=self.session.pk)
        self.assertEqual("room-2", row.channel_name)
        self.assertEqual(99, row.request_count)
        self.assertFalse(row.connected)

    def test_change_channel_refreshes_updated_on(self):
        before = WebSocketSession.objects.get(pk=self.session.pk).updated_on
        view = views.WebSocketView()
        view.websocket_session = WebSocketSession.objects.get(pk=self.session.pk)
        view.body = {"channel": "room-2"}

        view.change_channel(self._request())

        self.assertGreater(
            WebSocketSession.objects.get(pk=self.session.pk).updated_on, before
        )

    def test_disconnect_changes_only_the_connected_flag_in_one_query(self):
        self._concurrent_update(channel_name="room-9", request_count=42)
        view = views.WebSocketView(api_gateway=self.session.api_gateway)

        with self.assertNumQueries(1):
            response = view.disconnect(self._request())

        row = WebSocketSession.objects.get(pk=self.session.pk)
        self.assertIsNone(response)
        self.assertFalse(row.connected)
        self.assertEqual("room-9", row.channel_name)
        self.assertEqual(42, row.request_count)

    def test_disconnect_refreshes_updated_on(self):
        before = WebSocketSession.objects.get(pk=self.session.pk).updated_on

        views.WebSocketView(api_gateway=self.session.api_gateway).disconnect(
            self._request()
        )

        self.assertGreater(
            WebSocketSession.objects.get(pk=self.session.pk).updated_on, before
        )

    def test_disconnect_for_an_unknown_connection_is_a_400_and_writes_nothing(self):
        request = self._request()
        request.META["HTTP_CONNECTIONID"] = "UNKNOWN"

        with self.assertNumQueries(1):
            response = views.WebSocketView().disconnect(request)

        self.assertEqual(400, response.status_code)


class WebSocketViewConfiguredSettingsTestCase(TestCase):
    """The ``WEBSOCKETS`` settings are all read the same way, and each one takes effect."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="conf-user", password="pw")

    # token expiry

    def _token_post(self):
        request = self.factory.post("/")
        request.user = self.user
        request.session = MagicMock(session_key="session-key")
        return views.WebSocketTokenView().post(request)

    def test_the_token_endpoint_reports_the_default_expiry(self):
        with override_settings(WEBSOCKETS={}):
            self.assertEqual(60, json.loads(self._token_post().content)["expires_in"])

    @override_settings(WEBSOCKETS={"token_expiry_seconds": 15})
    def test_the_token_endpoint_reports_the_configured_expiry(self):
        self.assertEqual(15, json.loads(self._token_post().content)["expires_in"])

    def _connect_with_token_aged(self, seconds):
        from datetime import timedelta

        from django.utils import timezone

        token = WebSocketToken.generate_token(self.user, "session-key")
        WebSocketToken.objects.filter(pk=token.pk).update(
            created_at=timezone.now() - timedelta(seconds=seconds)
        )
        request = RequestFactory().post(
            "/",
            QUERY_STRING=f"ws_token={token.token}&channel=room-1",
            HTTP_HOST="www.example.com",
            HTTP_CONNECTIONID="CONNECTION-123",
            HTTP_USER_AGENT="AmazonAPIGateway_APIGateway-1",
            HTTP_X_AMZN_APIGATEWAY_API_ID="APIGateway-1",
            HTTP_COOKIE="c",
            HTTP_ORIGIN="https://www.example.com",
            HTTP_SEC_WEBSOCKET_EXTENSIONS="e",
            HTTP_SEC_WEBSOCKET_KEY="k",
            HTTP_SEC_WEBSOCKET_VERSION="1",
            HTTP_X_FORWARDED_FOR="123.123.123.123",
        )
        request.user = AnonymousUser()
        request.session = MagicMock(session_key="session-key")
        view = views.WebSocketView()
        view.api_gateway = None
        view.RATE_LIMIT_ENABLED = False
        return view.connect(request, route="connect")

    @override_settings(ALLOWED_HOSTS=["www.example.com"], WEBSOCKETS={})
    def test_a_token_older_than_the_default_expiry_is_refused(self):
        self.assertEqual(400, self._connect_with_token_aged(90).status_code)

    @override_settings(
        ALLOWED_HOSTS=["www.example.com"], WEBSOCKETS={"token_expiry_seconds": 120}
    )
    def test_a_longer_configured_expiry_is_honoured(self):
        """Clients were told 120 seconds but tokens were refused after 60."""
        self.assertEqual(200, self._connect_with_token_aged(90).status_code)

    @override_settings(
        ALLOWED_HOSTS=["www.example.com"], WEBSOCKETS={"token_expiry_seconds": 10}
    )
    def test_a_shorter_configured_expiry_is_enforced(self):
        """A shorter window was reported to clients but not applied."""
        self.assertEqual(400, self._connect_with_token_aged(30).status_code)

    @override_settings(ALLOWED_HOSTS=["www.example.com"], WEBSOCKETS={})
    def test_a_fresh_token_is_accepted(self):
        self.assertEqual(200, self._connect_with_token_aged(1).status_code)

    # the other settings

    @override_settings(WEBSOCKETS={"token_rate_limit_per_minute": 1})
    def test_the_token_rate_limit_setting_is_applied(self):
        self.assertEqual(200, self._token_post().status_code)
        self.assertEqual(403, self._token_post().status_code)

    @override_settings(
        WEBSOCKETS={"rate_limit_max_attempts": 7, "rate_limit_window_minutes": 3}
    )
    def test_the_connection_rate_limit_settings_are_applied_to_a_view(self):
        view = views.WebSocketView()

        self.assertEqual(7, view.RATE_LIMIT_MAX_ATTEMPTS)
        self.assertEqual(3, view.RATE_LIMIT_WINDOW_MINUTES)

    @override_settings(WEBSOCKETS=None)
    def test_a_view_can_be_created_when_the_setting_is_none(self):
        view = views.WebSocketView()

        self.assertEqual(20, view.RATE_LIMIT_MAX_ATTEMPTS)
        self.assertEqual(1, view.RATE_LIMIT_WINDOW_MINUTES)

    def test_a_view_can_be_created_when_the_setting_is_missing(self):
        from django.conf import settings

        with override_settings():
            del settings.WEBSOCKETS

            view = views.WebSocketView()

        self.assertEqual(20, view.RATE_LIMIT_MAX_ATTEMPTS)

    @override_settings(WEBSOCKETS={"rate_limit_max_attempts": 7})
    def test_a_class_attribute_still_overrides_the_setting(self):
        class StrictView(views.WebSocketView):
            RATE_LIMIT_MAX_ATTEMPTS = 2

        self.assertEqual(2, StrictView().RATE_LIMIT_MAX_ATTEMPTS)
