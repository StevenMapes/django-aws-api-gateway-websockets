Testing
=======

This guide explains how to test applications that use
Django-AWS-API-Gateway-WebSockets.

The package lets you handle WebSocket events as normal Django HTTP requests
forwarded by AWS API Gateway. This means most application logic can be tested
with Django's existing test tools.

Testing strategy
----------------

A good test suite should cover:

* WebSocket view dispatch;
* connection handling;
* message handlers;
* permissions;
* channel access;
* WebSocket token behaviour;
* rate limiting;
* server-to-client sends;
* stale connection behaviour;
* management commands;
* client payload validation.

Most tests should avoid making real AWS calls. Mock the AWS API Gateway
Management API when testing message sending.

Run the project tests
---------------------

For this project, the test suite can be run with coverage.

.. code-block:: console

   coverage erase
   python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings
   coverage combine
   coverage report

If your application uses tox, run the relevant tox environment as well.

.. code-block:: console

   tox

Testing WebSocket views as Django views
---------------------------------------

AWS API Gateway forwards WebSocket events to Django as HTTP requests.

This means you can test a ``WebSocketView`` subclass with Django's test client
or request factory.

The main difference from a normal view test is that you need to include the
headers API Gateway would normally send.

Example test view
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ExampleWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           return JsonResponse(
               {
                   "ok": True,
                   "message": self.body.get("message"),
               }
           )

Example URL
~~~~~~~~~~~

.. code-block:: python

   from django.urls import path

   from .views import ExampleWebSocketView


   urlpatterns = [
       path(
           "ws/<slug:route>",
           ExampleWebSocketView.as_view(),
           name="example_websocket",
       ),
   ]

API Gateway test headers
------------------------

Your tests need to include the headers expected by the view.

A helper function keeps tests readable.

.. code-block:: python

   def api_gateway_headers(api_id="abc123", connection_id="connection-1"):
       return {
           "HTTP_HOST": "testserver",
           "HTTP_X_FORWARDED_FOR": "127.0.0.1",
           "HTTP_X_FORWARDED_PROTO": "https",
           "HTTP_CONNECTIONID": connection_id,
           "HTTP_USER_AGENT": f"AmazonAPIGateway_{api_id}",
           "HTTP_X_AMZN_APIGATEWAY_API_ID": api_id,
           "HTTP_X_AMZN_TRACE_ID": "Root=1-test",
           "HTTP_X_FORWARDED_PORT": "443",
           "HTTP_X_REAL_IP": "127.0.0.1",
       }

Connection requests may need additional WebSocket-specific headers.

.. code-block:: python

   def api_gateway_connect_headers(api_id="abc123", connection_id="connection-1"):
       headers = api_gateway_headers(api_id=api_id, connection_id=connection_id)
       headers.update(
           {
               "HTTP_COOKIE": "sessionid=test",
               "HTTP_ORIGIN": "https://testserver",
               "HTTP_SEC_WEBSOCKET_EXTENSIONS": "permessage-deflate",
               "HTTP_SEC_WEBSOCKET_KEY": "test-key",
               "HTTP_SEC_WEBSOCKET_VERSION": "13",
           }
       )
       return headers

Testing a message handler
-------------------------

Create the required API Gateway and WebSocket session records, then post a JSON
message to the view.

.. code-block:: python

   import json

   import pytest
   from django.test import Client

   from django_aws_api_gateway_websockets.models import ApiGateway
   from django_aws_api_gateway_websockets.models import WebSocketSession


   @pytest.mark.django_db
   def test_default_handler_returns_message():
       api_gateway = ApiGateway.objects.create(
           api_name="Test API",
           target_base_endpoint="https://testserver/ws/",
           api_id="abc123",
           api_created=True,
           stage_name="test",
       )

       WebSocketSession.objects.create(
           connection_id="connection-1",
           api_gateway=api_gateway,
           channel_name="testing",
       )

       client = Client()

       response = client.post(
           "/ws/default",
           data=json.dumps(
               {
                   "action": "default",
                   "message": "Hello",
               }
           ),
           content_type="application/json",
           **api_gateway_headers(
               api_id="abc123",
               connection_id="connection-1",
           ),
       )

       assert response.status_code == 200
       assert response.json()["ok"] is True
       assert response.json()["message"] == "Hello"

Testing connection handling
---------------------------

Connection tests should verify that a ``WebSocketSession`` is created when a
client connects.

For a simple test, disable WebSocket token validation on the test view.

.. code-block:: python

   import pytest
   from django.test import Client

   from django_aws_api_gateway_websockets.models import ApiGateway
   from django_aws_api_gateway_websockets.models import WebSocketSession


   @pytest.mark.django_db
   def test_connect_creates_websocket_session():
       ApiGateway.objects.create(
           api_name="Test API",
           target_base_endpoint="https://testserver/ws/",
           api_id="abc123",
           api_created=True,
           stage_name="test",
       )

       client = Client()

       response = client.post(
           "/ws/connect?channel=general",
           data="",
           content_type="application/json",
           **api_gateway_connect_headers(
               api_id="abc123",
               connection_id="connection-1",
           ),
       )

       assert response.status_code == 200

       session = WebSocketSession.objects.get(connection_id="connection-1")
       assert session.channel_name == "general"
       assert session.connected is True

Testing disconnection
---------------------

Disconnection tests should verify that the session is marked as disconnected.

.. code-block:: python

   import pytest
   from django.test import Client

   from django_aws_api_gateway_websockets.models import ApiGateway
   from django_aws_api_gateway_websockets.models import WebSocketSession


   @pytest.mark.django_db
   def test_disconnect_marks_session_disconnected():
       api_gateway = ApiGateway.objects.create(
           api_name="Test API",
           target_base_endpoint="https://testserver/ws/",
           api_id="abc123",
           api_created=True,
           stage_name="test",
       )

       WebSocketSession.objects.create(
           connection_id="connection-1",
           api_gateway=api_gateway,
           channel_name="general",
           connected=True,
       )

       client = Client()

       response = client.post(
           "/ws/disconnect",
           data="",
           content_type="application/json",
           **api_gateway_headers(
               api_id="abc123",
               connection_id="connection-1",
           ),
       )

       assert response.status_code == 200

       session = WebSocketSession.objects.get(connection_id="connection-1")
       assert session.connected is False

Testing handler selection
-------------------------

If your view exposes multiple handlers, test that the correct handler is called.

Example view:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       ALLOWED_HANDLERS = {
           "default",
           "chat_message",
           "fetch_history",
       }

       def chat_message(self, request, *args, **kwargs):
           return JsonResponse({"handler": "chat_message"})

       def fetch_history(self, request, *args, **kwargs):
           return JsonResponse({"handler": "fetch_history"})

       def default(self, request, *args, **kwargs):
           return JsonResponse({"handler": "default"})

Example tests:

.. code-block:: python

   @pytest.mark.django_db
   def test_chat_message_handler_is_selected(client, api_gateway, websocket_session):
       response = client.post(
           "/ws/default",
           data=json.dumps({"action": "chat_message"}),
           content_type="application/json",
           **api_gateway_headers(),
       )

       assert response.status_code == 200
       assert response.json()["handler"] == "chat_message"


   @pytest.mark.django_db
   def test_fetch_history_handler_is_selected(client, api_gateway, websocket_session):
       response = client.post(
           "/ws/default",
           data=json.dumps({"action": "fetch_history"}),
           content_type="application/json",
           **api_gateway_headers(),
       )

       assert response.status_code == 200
       assert response.json()["handler"] == "fetch_history"

Testing permissions
-------------------

Test permission-protected views with:

* anonymous users;
* authenticated users without permissions;
* authenticated users with required permissions;
* users with only some required permissions;
* object-level access checks.

Example:

.. code-block:: python

   import json

   import pytest
   from django.contrib.auth.models import Permission
   from django.test import Client


   @pytest.mark.django_db
   def test_user_without_permission_is_denied(django_user_model):
       user = django_user_model.objects.create_user(
           username="alice",
           password="password",
       )

       client = Client()
       client.force_login(user)

       response = client.post(
           "/ws/default",
           data=json.dumps({"action": "restricted"}),
           content_type="application/json",
           **api_gateway_headers(),
       )

       assert response.status_code in [400, 403]


   @pytest.mark.django_db
   def test_user_with_permission_is_allowed(django_user_model):
       user = django_user_model.objects.create_user(
           username="alice",
           password="password",
       )

       permission = Permission.objects.get(codename="can_use_chat")
       user.user_permissions.add(permission)

       client = Client()
       client.force_login(user)

       response = client.post(
           "/ws/default",
           data=json.dumps({"action": "restricted"}),
           content_type="application/json",
           **api_gateway_headers(),
       )

       assert response.status_code == 200

The exact permission setup depends on your application models and permission
names.

See :doc:`permissions`.

Testing WebSocket tokens
------------------------

For token-protected connections, test the full token flow:

#. user logs in;
#. browser requests a token;
#. token is returned;
#. connection includes the token;
#. token is consumed;
#. token cannot be reused.

Example token request test:

.. code-block:: python

   import pytest
   from django.test import Client


   @pytest.mark.django_db
   def test_authenticated_user_can_request_websocket_token(django_user_model):
       user = django_user_model.objects.create_user(
           username="alice",
           password="password",
       )

       client = Client(enforce_csrf_checks=False)
       client.force_login(user)

       response = client.post("/api/ws-token/")

       assert response.status_code == 200
       assert "token" in response.json()
       assert response.json()["expires_in"] == 60

Example token reuse test:

.. code-block:: python

   import pytest

   from django_aws_api_gateway_websockets.models import WebSocketToken


   @pytest.mark.django_db
   def test_websocket_token_is_single_use(django_user_model):
       user = django_user_model.objects.create_user(username="alice")
       session_key = "test-session"

       token = WebSocketToken.generate_token(
           user=user,
           session_key=session_key,
       )

       first_user = WebSocketToken.validate_and_consume(
           token_value=token.token,
           session_key=session_key,
       )

       second_user = WebSocketToken.validate_and_consume(
           token_value=token.token,
           session_key=session_key,
       )

       assert first_user == user
       assert second_user is None

See :doc:`websocket_tokens`.

Testing rate limiting
---------------------

Test that repeated connection attempts are rejected when the configured limit is
exceeded.

.. code-block:: python

   import pytest

   from django_aws_api_gateway_websockets.models import ConnectionRateLimit


   @pytest.mark.django_db
   def test_connection_rate_limit_blocks_excess_attempts():
       ip_address = "127.0.0.1"

       for _ in range(20):
           ConnectionRateLimit.record_attempt(
               ip_address=ip_address,
               successful=False,
           )

       allowed, attempt_count = ConnectionRateLimit.check_rate_limit(
           ip_address=ip_address,
           max_attempts=20,
           window_minutes=5,
       )

       assert allowed is False
       assert attempt_count == 20

See :doc:`rate_limiting`.

Mocking message sending
-----------------------

Tests should not normally call the real AWS API Gateway Management API.

Mock Boto3 when testing ``send_message``.

Example with ``unittest.mock``:

.. code-block:: python

   from unittest.mock import Mock
   from unittest.mock import patch

   import pytest

   from django_aws_api_gateway_websockets.models import ApiGateway
   from django_aws_api_gateway_websockets.models import WebSocketSession


   @pytest.mark.django_db
   def test_send_message_posts_to_connection(settings):
       settings.AWS_GATEWAY_REGION_NAME = "eu-west-1"

       api_gateway = ApiGateway.objects.create(
           api_name="Test API",
           target_base_endpoint="https://testserver/ws/",
           api_id="abc123",
           api_created=True,
           stage_name="test",
       )

       session = WebSocketSession.objects.create(
           connection_id="connection-1",
           api_gateway=api_gateway,
           channel_name="general",
       )

       client = Mock()
       client.post_to_connection.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

       with patch(
           "django_aws_api_gateway_websockets.models.get_boto3_client",
           return_value=client,
       ):
           session.send_message(
               {
                   "type": "test",
                   "message": "Hello",
               }
           )

       client.post_to_connection.assert_called_once()

Testing broadcast behaviour
---------------------------

When testing queryset sends, create multiple sessions and mock the AWS client.

.. code-block:: python

   from unittest.mock import Mock
   from unittest.mock import patch

   import pytest

   from django_aws_api_gateway_websockets.models import ApiGateway
   from django_aws_api_gateway_websockets.models import WebSocketSession


   @pytest.mark.django_db
   def test_send_message_to_channel(settings):
       settings.AWS_GATEWAY_REGION_NAME = "eu-west-1"

       api_gateway = ApiGateway.objects.create(
           api_name="Test API",
           target_base_endpoint="https://testserver/ws/",
           api_id="abc123",
           api_created=True,
           stage_name="test",
       )

       WebSocketSession.objects.create(
           connection_id="connection-1",
           api_gateway=api_gateway,
           channel_name="general",
           connected=True,
       )
       WebSocketSession.objects.create(
           connection_id="connection-2",
           api_gateway=api_gateway,
           channel_name="general",
           connected=True,
       )
       WebSocketSession.objects.create(
           connection_id="connection-3",
           api_gateway=api_gateway,
           channel_name="support",
           connected=True,
       )

       client = Mock()
       client.post_to_connection.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

       with patch(
           "django_aws_api_gateway_websockets.models.get_boto3_client",
           return_value=client,
       ):
           WebSocketSession.objects.filter(
               channel_name="general",
           ).send_message(
               {
                   "type": "test",
                   "message": "Hello general.",
               }
           )

       assert client.post_to_connection.call_count == 2

Testing stale connections
-------------------------

When AWS reports that a connection has gone away, your application should treat
that as normal operational behaviour.

You can test that stale sessions are handled by mocking the AWS client to raise
the relevant client error.

Example outline:

.. code-block:: python

   from botocore.exceptions import ClientError


   gone_error = ClientError(
       {
           "Error": {
               "Code": "GoneException",
               "Message": "Gone",
           }
       },
       "PostToConnection",
   )

Use this mocked error when testing stale connection handling.

Testing management commands
---------------------------

Use Django's ``call_command`` helper to test management commands.

Example for clearing disconnected sessions:

.. code-block:: python

   import pytest
   from django.core.management import call_command

   from django_aws_api_gateway_websockets.models import ApiGateway
   from django_aws_api_gateway_websockets.models import WebSocketSession


   @pytest.mark.django_db
   def test_clear_websocket_sessions_command():
       api_gateway = ApiGateway.objects.create(
           api_name="Test API",
           target_base_endpoint="https://testserver/ws/",
           api_id="abc123",
           api_created=True,
           stage_name="test",
       )

       WebSocketSession.objects.create(
           connection_id="connected",
           api_gateway=api_gateway,
           connected=True,
       )

       WebSocketSession.objects.create(
           connection_id="disconnected",
           api_gateway=api_gateway,
           connected=False,
       )

       call_command("clearWebSocketSessions")

       assert WebSocketSession.objects.filter(connection_id="connected").exists()
       assert not WebSocketSession.objects.filter(connection_id="disconnected").exists()

Testing cleanup commands
~~~~~~~~~~~~~~~~~~~~~~~~

You can also test token and rate limit cleanup with ``call_command``.

.. code-block:: python

   from django.core.management import call_command


   call_command(
       "cleanupWebSocketTokens",
       token_age=300,
       rate_limit_age=7,
   )

Testing API Gateway creation
----------------------------

Tests for API Gateway creation should mock AWS clients.

Do not create real AWS resources from unit tests.

Mock the Boto3 client and assert that the expected AWS client methods are called.

Example strategy:

* create an ``ApiGateway`` record;
* mock ``get_boto3_client``;
* configure mocked responses for API creation, routes, stages, and deployment;
* call ``api_gateway.create_gateway()``;
* assert the record is updated.

Testing client JavaScript
-------------------------

Client JavaScript can be tested separately using your preferred frontend testing
tools.

Important behaviours to test include:

* requesting a token before connecting;
* including ``ws_token`` in the WebSocket URL;
* including ``channel`` in the WebSocket URL;
* sending JSON messages with the expected action or handler;
* handling server-sent message types;
* reconnecting with a fresh token;
* changing rooms by closing and reconnecting;
* not sending while the socket is closed.

Test data cleanup
-----------------

WebSocket tests can create many operational records.

Use normal Django test database isolation where possible.

If you create records outside the test database lifecycle, clean up:

* WebSocket sessions;
* WebSocket tokens;
* rate limit records;
* API Gateway records;
* additional routes.

Recommended test coverage
-------------------------

A mature application test suite should include:

Views
~~~~~

* connection accepted;
* connection rejected when headers are missing;
* connection rejected when token is missing;
* connection rejected when token is reused;
* disconnection marks session disconnected;
* default handler works;
* custom handlers work;
* disallowed handlers are rejected.

Permissions
~~~~~~~~~~~

* anonymous user denied where expected;
* user without permission denied;
* user with required permission allowed;
* object-level access enforced;
* users cannot access another user's channel or tenant.

Messaging
~~~~~~~~~

* current session send works;
* channel send targets the correct sessions;
* broadcast send targets all connected sessions;
* disconnected sessions are ignored;
* stale sessions are handled.

Operations
~~~~~~~~~~

* cleanup commands remove expected records;
* rate limit records are created;
* rate limits reject excessive attempts;
* token cleanup removes expired tokens.

Testing tips
------------

Keep tests focused
~~~~~~~~~~~~~~~~~~

Test your own application logic separately from AWS infrastructure.

Mock AWS calls
~~~~~~~~~~~~~~

Do not create real API Gateway resources in unit tests.

Use fixtures
~~~~~~~~~~~~

Create fixtures for:

* API Gateway records;
* WebSocket sessions;
* test headers;
* authenticated users;
* WebSocket tokens.

Use clear payloads
~~~~~~~~~~~~~~~~~~

Keep JSON payloads explicit in tests so failures are easy to understand.

Test security failures
~~~~~~~~~~~~~~~~~~~~~~

Security-related tests are as important as successful-path tests.

Related pages
-------------

See also:

* :doc:`quickstart`;
* :doc:`concepts`;
* :doc:`security`;
* :doc:`websocket_tokens`;
* :doc:`permissions`;
* :doc:`rate_limiting`;
* :doc:`message_patterns`;
* :doc:`troubleshooting`;
* :doc:`models`.
