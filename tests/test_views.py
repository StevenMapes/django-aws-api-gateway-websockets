import json
from unittest.mock import MagicMock, patch

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
        self.assertEqual(
            (
                f"Some of the required headers are missing; Expected {obj.required_headers}, "
                f"Received {request.headers.keys()}"
            ).encode("utf-8"),
            res.content,
        )

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
        self.assertEqual(
            (
                f"Unexpected Useragent; Expected {obj.expected_useragent_prefix}{obj.aws_api_gateway_id}, "
                f"Received {request.headers['User-Agent']}"
            ).encode("utf-8"),
            res.content,
        )

    def test__expected_headers(self):
        """Ensure the methods returns True when all headers are present otherwise should return Fakse"""
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

    def test__expected_useragent_returns_true_for_normal_browser_useragent(
        self,
    ):
        """
        If the aws_api_gateway_id is set and the user agent is not the expected one, I.E ending with it, then the
        method should return False
        """
        allowed_api_id = "ABC123AB"

        post_data = {"action": "default", "key": "value"}
        request = self.factory.post(
            "",
            data=json.dumps(post_data),
            content_type="application/json",
            HTTP_USER_AGENT=f"AmazonAPIGateway_ANOTHER_ID",
        )

        obj = views.WebSocketView()
        obj.aws_api_gateway_id = allowed_api_id

        self.assertTrue(obj._expected_useragent(request=request))
