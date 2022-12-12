import json
from typing import Union

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from django_aws_api_gateway_websockets.models import ApiGateway, WebSocketSession


@method_decorator(csrf_exempt, name="dispatch")
class WebSocketView(View):
    """The base WebSocket View for handling messages sent from the client via AWS API Gateway.
    Expects a URL slug parameter called route
    """

    debug = False
    debug_log = None
    route_selection_key = "action"
    model = None
    body = {}
    aws_api_gateway_id = None  # Set to None to allow all
    api_gateway = None
    websocket_session = None
    required_headers = [
        "Host",
        "X-Forwarded-For",
        "X-Forwarded-Proto",
        "Content-Length",
        "Connectionid",
        "User-Agent",
        "X-Amzn-Apigateway-Api-Id",
    ]
    additional_required_headers = [
        "Connection",
        "X-Amzn-Trace-Id",
        "X-Forwarded-Port",
        "X-Real-Ip",
    ]
    required_connection_headers = [
        "Cookie",
        "Origin",
        "Sec-Websocket-Extensions",
        "Sec-Websocket-Key",
        "Sec-Websocket-Version",
    ]
    expected_useragent_prefix = "AmazonAPIGateway_"

    def __init__(self, **kwargs):
        self.api_gateway = kwargs.get("api_gateway", False)
        self.websocket_session = kwargs.get("websocket_session", False)
        self.debug = kwargs.get("debug", False)
        self.debug_log = []
        super().__init__(**kwargs)

    def _debug(self, msg: str):
        if self.debug:
            self.debug_log.append(msg)

    def setup(self, request, *args, **kwargs):
        """Converts the request.body string back into a dictionary and assign to the objects body property for ease"""
        super().setup(request, *args, **kwargs)
        self._debug("Within setup")
        self.body = json.loads(request.body) if request.body else {}
        self._debug("Setup completed")

    def _return_bad_request(self, msg):
        """Common method for logging and returning the HTTP400 response"""
        self._debug(f"_return_bad_request passed {msg}")
        return HttpResponseBadRequest(msg)

    def route_selection_key_missing(
        self, request, *args, **kwargs
    ) -> HttpResponseBadRequest:
        """Method for handling missing route_selection_key"""
        msg = f"route_select_key {self.route_selection_key} missing from request body."
        return self._return_bad_request(msg)

    def missing_headers(self, request, *args, **kwargs) -> HttpResponseBadRequest:
        """Method for handling missing headers"""
        msg = (
            f"Some of the required headers are missing; Expected {self.required_headers}, "
            f"Received {request.headers.keys()}"
        )
        return self._return_bad_request(msg)

    def invalid_useragent(self, request, *args, **kwargs) -> HttpResponseBadRequest:
        """Method for handling unexpected useragents"""
        msg = (
            f"Unexpected Useragent; Expected {self.expected_useragent_prefix}{self.aws_api_gateway_id}, "
            f"Received {request.headers['User-Agent']}"
        )
        return self._return_bad_request(msg)

    def _expected_headers(self, request, *args, **kwargs) -> bool:
        """Ensure that all required headers exist within the request header"""
        request_headers = request.headers.keys()
        res = all(h in request_headers for h in self.required_headers)

        if res and self.additional_required_headers:
            res = all(h in request_headers for h in self.additional_required_headers)

        self._debug(f"_expected_headers() returned {res}")
        return res

    def _allowed_apigateway(self, request, *args, **kwargs) -> bool:
        """Ensure the AWS API Gateway is the expected one (if set against the class) otherwise use the DB check"""
        res = self._check_platform_registered_api_gateways(request)
        if self.aws_api_gateway_id:
            res = self.aws_api_gateway_id == request.headers["X-Amzn-Apigateway-Api-Id"]
            self._debug(f"_expected_apigateway_id() returned {res}")
        self._debug(f"_allowed_apigateway() returned {res}")
        return res

    def _check_platform_registered_api_gateways(self, request) -> bool:
        """Checks to ensure that the API Gateway calling the view is one that the user has registered"""
        self.api_gateway = ApiGateway.objects.filter(
            api_id=request.headers["X-Amzn-Apigateway-Api-Id"]
        ).first()
        self._debug(
            f"_check_platform_registered_api_gateways() returned {bool(self.api_gateway)}"
        )
        return bool(self.api_gateway)

    def _expected_useragent(self, request, *args, **kwargs) -> bool:
        """Validated that the useragent is the expected one for all calls except the connect method

        For the connect method the useragent should be API Gateway itself and NOT the client's forwarded useragent
        """
        if self.aws_api_gateway_id:
            res = (
                not request.headers["User-Agent"]
                == f"{self.expected_useragent_prefix}{self.aws_api_gateway_id}"
            )
        else:
            res = self.expected_useragent_prefix in request.headers["User-Agent"]
        self._debug(f"_expected_useragent() returned {res}")

        return res

    @staticmethod
    def _check_allowed_hosts(request) -> bool:
        """Check that the host is within the allowed hosts"""
        if (
            settings.ALLOWED_HOSTS
            and request.headers["Host"] not in settings.ALLOWED_HOSTS
        ):
            return False
        return True

    @staticmethod
    def _check_host_is_in_origin(request) -> bool:
        """Check that the value of the Host header is within the Origin header. Origin will have the protocol as well"""
        if request.headers["Host"] not in request.headers["Origin"]:
            return False
        return True

    def _expected_connection_headers(self, request, *args, **kwargs) -> bool:
        """Run additional checks for the connection route for security"""
        request_headers = request.headers.keys()

        return all(h in request_headers for h in self.required_connection_headers)

    def _add_user_to_request(self, request):
        """Fetch the user from the model and append it back into the request variable"""
        wss = WebSocketSession.objects.get(
            connection_id=request.headers["Connectionid"]
        )
        if wss.user:
            request.user = wss.user
        wss.request_count += 1
        wss.save()

    def _get_channel_name(self, request) -> str:
        """Returns the name of the channel to use

        The "channel" can be optionally be set as a querystring parameter during the connection. If it is not but the
        api_gateway that was selected has a default_channel_name set then that will be used instead. Otherwise an empty
        string is returned
        """
        channel_name = request.GET.get("channel", "")
        if (
            not channel_name
            and self.api_gateway
            and self.api_gateway.default_channel_name
        ):
            channel_name = self.api_gateway.default_channel_name

        return channel_name

    def _load_session(self, request):
        self.websocket_session = WebSocketSession.objects.get(
            connection_id=request.headers["Connectionid"]
        )

    def dispatch(self, request, *args, **kwargs):
        """Determine the correct method to call. The method will map to the route_selection_key or default.

        Checks for the expected headers.
        Tries to dispatch to the right method; if a method doesn't exist defer to the default handler.
        If the Route Selection Key is missing defer to the route selection error handler.
        If the request method isn't on the approved list then defer to the normal error handler .
        """
        if self._expected_headers(request) and self._allowed_apigateway(request):
            if request.method.lower() in self.http_method_names:
                if "connect" == self.kwargs.get("route"):
                    handler = self.connect
                elif "disconnect" == self.kwargs.get("route"):
                    if not self._expected_useragent(request, *args, **kwargs):
                        handler = self.invalid_useragent
                    else:
                        handler = self.disconnect
                        self._add_user_to_request(request)
                elif self.route_selection_key in self.body:
                    self._load_session(request)

                    handler = getattr(
                        self, self.body[self.route_selection_key], self.default
                    )
                    if not self._expected_useragent(request, *args, **kwargs):
                        handler = self.invalid_useragent
                    else:
                        self._add_user_to_request(request)
                else:
                    handler = self.route_selection_key_missing
            else:
                handler = self.http_method_not_allowed
        else:
            handler = self.missing_headers
        res = handler(request, *args, **kwargs)
        return res if res else JsonResponse({})

    def connect(
        self, request, *args, **kwargs
    ) -> Union[JsonResponse, HttpResponseBadRequest]:
        """Handle the connection route in a standard way that ensures the User to Connectionid mapping persists"""
        if not self._expected_connection_headers(request, *args, **kwargs):
            msg = f"Missing headers; Expected {self.required_connection_headers}, Received {request.headers}"
            return self._return_bad_request(msg)

        if not self._check_allowed_hosts(request):
            msg = f"Host {request.headers['Host']} not in AllowedHosts {settings.ALLOWED_HOSTS}"
            return self._return_bad_request(msg)

        if not self._check_host_is_in_origin(request):
            msg = f"Host {request.headers['Host']} not in Origin {request.headers['Origin']}"
            return self._return_bad_request(msg)

        res, msg = self._additional_connection_checks(request, *args, **kwargs)
        if not res:
            return self._return_bad_request(msg)

        WebSocketSession.objects.create(
            connection_id=request.headers["Connectionid"],
            channel_name=self._get_channel_name(request),
            user=request.user if request.user.is_authenticated else None,
            api_gateway=self.api_gateway,
        )

        return JsonResponse({})

    def _additional_connection_checks(self, request, *args, **kwargs) -> (bool, str):
        """Could add in additional steps for certificates, APIGateway Authorizers etc"""
        return True, ""

    def disconnect(self, request, *args, **kwargs):
        """Using connectionId update websocket table to show as disconnected"""
        wss = WebSocketSession.objects.get(
            connection_id=request.headers["Connectionid"]
        )
        wss.connected = False
        wss.save()

    def default(self, request, *args, **kwargs) -> JsonResponse:
        """Overload this method if you want to have a default message handler"""
        raise NotImplementedError("This logic needs to be defined within the subclass")
