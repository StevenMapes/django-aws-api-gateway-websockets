import json
from unittest.mock import MagicMock, patch

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from django_aws_api_gateway_websockets import views
from django_aws_api_gateway_websockets.models import ApiGateway


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
        obj = views.WebSocketView()
        res = obj._return_bad_request(msg)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)

    def test_route_selection_key_missing(self):
        """Ensure the expected response is generated when the route selection key is missing"""
        obj = views.WebSocketView()
        res = obj.route_selection_key_missing(None)

        self.assertIsInstance(res, HttpResponseBadRequest)
        self.assertEqual(400, res.status_code)
        self.assertEqual(
            b"route_select_key action missing from request body.", res.content
        )

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
        self.assertEqual(b"Some of the required headers are missing", res.content)

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

    def test__expected_useragent_returns_true_when_aws_api_key_is_set_and_is_in_the_user_agent(
        self,
    ):
        """_expected_useragent should return False if the AWS API Gateway is making the request

        That is determined by the useragent matching a particular string of "AmazonAPIGateway_" followed the API ID
        of the API Gateway. Only the "connect" call should use that user agent, all other connections should either
        use the REAL client useragent or nothing. In this test we are testing as if the API Gateway user agent was used
        """
        allowed_api_id = "ABC123AB"

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"AmazonAPIGateway_{allowed_api_id}",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id

        self.assertFalse(obj._expected_useragent(request=request))

    def test__expected_useragent_returns_true_when_useragent_is_not_the_exepcted_api_gateways_useragent(
        self,
    ):
        """
        If the aws_api_gateway_id is set and the useragent is NOT the useragent we expect to receive from the API Gateway
        I.E AmazonAPIGateway_ then a API Gateway ID, then the method should return True
        """
        allowed_api_id = "ABC123AB"

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT="AmazonAPIGateway_ANOTHER_ID",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id

        self.assertTrue(obj._expected_useragent(request=request))

    def test__expected_useragent_returns_false_when_useragent_is_not_the_exepcted_api_gateways_useragent(
        self,
    ):
        """
        If the aws_api_gateway_id is set and the user agent is the useragent we expect to receive from the API Gateway
        I.E where the useragent is AmazonAPIGateway_ then a API Gateway ID, then the method should return False
        """
        allowed_api_id = "ABC123AB"

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"AmazonAPIGateway_{allowed_api_id}",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id

        self.assertFalse(obj._expected_useragent(request=request))

    def test__expected_useragent_with_no_allowed_api_id_but_an_apigateway_made_the_call__should_return_true(
        self,
    ):
        """
        If the aws_api_gateway_id is set and the user agent is the useragent we expect to receive from the API Gateway
        I.E where the useragent is AmazonAPIGateway_ then a API Gateway ID, then the method should return False
        """
        allowed_api_id = ""

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"AmazonAPIGateway_SomeOtherId",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id

        self.assertTrue(obj._expected_useragent(request=request))

    def test__expected_useragent_with_no_allowed_api_id_and_an_apigateway_didnt_make_the_call__should_return_false(
        self,
    ):
        """
        If the aws_api_gateway_id is not set and the user agent is a normal user then False should be returned
        """
        allowed_api_id = ""

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"Mozzila/5.0",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id

        self.assertFalse(obj._expected_useragent(request=request))

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
    def test__add_user_to_request_raises_when_object_not_found(
        self, MockWebSocketSession
    ):
        """An exception should be raised if the object can not be found"""
        MockWebSocketSession.objects.get.side_effect = ObjectDoesNotExist(
            "no match found"
        )

        con_id = "12345"

        obj = views.WebSocketView()
        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid=con_id,
        )

        self.assertFalse(hasattr(request, "user"))
        with self.assertRaises(ObjectDoesNotExist):
            obj._add_user_to_request(request)

            MockWebSocketSession.objects.get.assert_called_with(
                connection_id=request.headers["Connectionid"]
            )

            self.assertFalse(hasattr(request, "user"))

    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test__add_user_to_request_when_session_found(self, MockWebSocketSession):
        """When a WebSocketSession is found then the user will be added to the request IF it's set against the session"""
        mocked_user = MagicMock(pk=12)
        configs = [
            {"name": "No User in session", "user": None},
            {"name": "User set in session", "user": mocked_user},
        ]

        for config in configs:
            with self.subTest(config=config):
                wss = MagicMock(user=config["user"], request_count=0)
                MockWebSocketSession.objects.get.return_value = wss
                con_id = "12345"

                obj = views.WebSocketView()
                request = self.factory.post(
                    "",
                    data=json.dumps({}),
                    content_type="application/json",
                    HTTP_Connectionid=con_id,
                )

                self.assertFalse(hasattr(request, "user"))
                obj._add_user_to_request(request)

                MockWebSocketSession.objects.get.assert_called_with(
                    connection_id=request.headers["Connectionid"]
                )

                if config["user"]:
                    self.assertTrue(hasattr(request, "user"))
                    self.assertEqual(mocked_user, request.user)
                    self.assertEqual(1, wss.request_count)
                else:
                    self.assertFalse(hasattr(request, "user"))
                    self.assertEqual(1, wss.request_count)

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
        obj._load_session(request)

        MockWebSocketSession.objects.get.assert_called_with(connection_id="1234")
        self.assertEqual(
            obj.websocket_session, MockWebSocketSession.objects.get.return_value
        )

    def test__additional_connection_checks(self):
        """The _additional_connection_checks method should return True, "" for the default implementation"""
        obj = views.WebSocketView()
        result, msg = obj._additional_connection_checks(None)
        self.assertTrue(result)
        self.assertEqual("", msg)

    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    def test_disconnect(self, MockWebSocketSession):
        """The disconnect method should load the websocket session, update a property then call the save method"""
        wss = MagicMock(connected=True)
        MockWebSocketSession.objects.get.return_value = wss

        request = self.factory.post(
            "",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_Connectionid="1234",
        )
        obj = views.WebSocketView()

        self.assertTrue(wss.connected)

        obj.disconnect(request)

        MockWebSocketSession.objects.get.assert_called_with(
            connection_id=request.headers["Connectionid"]
        )
        MockWebSocketSession.objects.get.return_value.save.assert_called_with()
        self.assertFalse(MockWebSocketSession.objects.get.return_value.connected)

    def test_default(self):
        """The method handling default actions should raise a NotImplemented error by default"""
        obj = views.WebSocketView()

        with self.assertRaises(NotImplementedError) as e:
            obj.default(request=self.factory.get(""))
        self.assertEqual(
            "This logic needs to be defined within the subclass", str(e.exception)
        )

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_connect(self, MockJsonResponse, MockWebSocketSession):
        """Test the connect method when the expected header are set. Should pass through all checks"""
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
        obj = views.WebSocketView()

        res = obj.connect(request)
        MockWebSocketSession.objects.create.assert_called_with(
            connection_id=request.headers["Connectionid"],
            channel_name=obj._get_channel_name(request),
            user=request.user if request.user.is_authenticated else None,
            api_gateway=obj.api_gateway,
        )
        MockJsonResponse.assert_called_with({})
        self.assertEqual(MockJsonResponse.return_value, res)

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    def test_connect__missing_expected_headers(
        self, MockHttpResponseBadRequest, MockJsonResponse, MockWebSocketSession
    ):
        """Test the connect method when the expected headers are missing."""
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

        res = obj.connect(request)

        self.assertEqual(MockHttpResponseBadRequest.return_value, res)
        self.assertEqual(0, MockWebSocketSession.objects.create.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        MockHttpResponseBadRequest.assert_called_with("Missing 3 headers")

    @override_settings(ALLOWED_HOSTS=["www.example.com"])
    @patch("django_aws_api_gateway_websockets.views.WebSocketSession")
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    @patch("django_aws_api_gateway_websockets.views.HttpResponseBadRequest")
    def test_connect__with_invalid_host(
        self, MockHttpResponseBadRequest, MockJsonResponse, MockWebSocketSession
    ):
        """Test the connect method when the host is not in the allowed list are missing."""
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
    def test_connect__with_host_not_in_origin(
        self, MockHttpResponseBadRequest, MockJsonResponse, MockWebSocketSession
    ):
        """Test the connect method when the host does not exist within the origin."""
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
    def test_connect__additional_connection_checks_returns_false(
        self, MockHttpResponseBadRequest, MockJsonResponse, MockWebSocketSession
    ):
        """Test the connect method when the expected headers are missing."""
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

        MockHttpResponseBadRequest.assert_called_with(
            "Some of the required headers are missing"
        )
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
        "django_aws_api_gateway_websockets.views.WebSocketView.route_selection_key_missing"
    )
    @patch("django_aws_api_gateway_websockets.views.JsonResponse")
    def test_dispatch__route_selection_key_missing(
        self,
        MockJsonResponse,
        mocked_route_selection_key_missing,
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

        self.assertEqual(res, mocked_route_selection_key_missing.return_value)

        mocked_route_selection_key_missing.assert_called_with(request, route="chat")

        self.assertEqual(0, mocked__load_session.call_count)
        self.assertEqual(0, mocked__expected_useragent.call_count)
        self.assertEqual(0, mock_invalid_useragent.call_count)
        self.assertEqual(0, mocked_disconnect.call_count)
        self.assertEqual(0, MockJsonResponse.call_count)
        self.assertEqual(0, mocked__add_user_to_request.call_count)
