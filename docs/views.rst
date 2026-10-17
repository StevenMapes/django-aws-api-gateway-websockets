#####
Views
#####

The package has two views. ``WebSocketView`` receives the requests that API Gateway sends for each WebSocket event, and ``WebSocketTokenView`` gives a browser the one-time token it needs to connect.

Both are in ``django_aws_api_gateway_websockets.views``. This page describes how they behave and what you can change. For the generated signatures, see :doc:`api/index`.

``WebSocketTokenView``
======================

Returns a one-time token for the logged-in user. The browser puts the token in the WebSocket URL, and the connect route spends it. See :doc:`websocket_tokens` for the full flow.

.. code-block:: python

   from django.urls import path

   from django_aws_api_gateway_websockets.views import WebSocketTokenView

   urlpatterns = [
       path("ws/token/", WebSocketTokenView.as_view(), name="ws-token"),
   ]

The view accepts ``POST`` only. Django's CSRF middleware protects it, so the browser must send the CSRF token. The user must be logged in.

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Status
     - Meaning
   * - 200
     - A JSON body with ``token`` and ``expires_in``, which is the number of seconds the token is valid for.
   * - 403
     - The user is not logged in (``Authentication required``), has asked for too many tokens (``Rate limit exceeded``), or the CSRF check failed.
   * - 405
     - The method is not allowed. Only ``POST`` returns a token.

The number of tokens a user can ask for each minute is ``token_rate_limit_per_minute``, and the lifetime of a token is ``token_expiry_seconds``. Both are keys of the ``WEBSOCKETS`` setting. See :doc:`settings`.

``WebSocketView``
=================

The base class for the view that API Gateway calls. Subclass it, add handler methods, and route it with a URL that has a slug named ``route``:

.. code-block:: python

   from django.http import JsonResponse
   from django.urls import path

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       def default(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

       def chat_message(self, request, *args, **kwargs):
           text = str(self.body.get("message", "")).strip()
           return JsonResponse({"ok": bool(text)})


   urlpatterns = [
       path("ws/<slug:route>", ChatWebSocketView.as_view(), name="ws"),
   ]

The view is exempt from CSRF checks, because API Gateway cannot send a CSRF token. It relies on the checks below instead, and on the :doc:`gateway_secret` if you set one.

Routes
------

API Gateway calls the URL once for each route, and the ``route`` part of the URL says which.

``connect``
   A client opens the WebSocket. The view checks the request, spends the token, and creates a ``WebSocketSession``.

``disconnect``
   A client closes the WebSocket. The view marks its session as not connected.

Any other route
   A message from a connected client. The view loads the session and calls one handler method. This includes the ``default`` route and every additional route you have added. See :doc:`adding_new_routes`.

How a request is handled
------------------------

``dispatch`` runs these steps in order. The first step that fails decides the response.

#. **Gateway secret.** If ``WEBSOCKETS["gateway_secret"]`` is set, the ``X-Ws-Gateway-Secret`` header must match it. If not, the response is 403 and nothing else runs, not even a database query.
#. **Headers and gateway.** Every header in ``required_headers`` and ``additional_required_headers`` must be present, and the ``X-Amzn-Apigateway-Api-Id`` header must name an ``ApiGateway`` record, or the gateway in ``aws_api_gateway_id`` if you set one. If not, the response is 400.
#. **HTTP method.** It must be in ``http_method_names``, otherwise the response is 405.
#. **The route.** What happens next depends on the route.

On ``connect``:

#. If ``CHECK_CONNECT_USERAGENT`` is ``True``, the ``User-Agent`` must be the one API Gateway sends, the prefix in ``expected_useragent_prefix`` followed by the API ID. It is ``False`` by default. See :ref:`useragent-check`.
#. The connection rate limit is checked, if ``RATE_LIMIT_ENABLED`` is ``True``.
#. The headers in ``required_connection_headers`` must be present, and the ``Connectionid`` must be valid.
#. The host must be in ``ALLOWED_HOSTS`` and in the ``Origin`` header.
#. The channel must be valid.
#. If ``USE_WS_TOKEN`` is ``True``, the ``ws_token`` query string value must be a valid token for the browser's session. The token is spent, and its user becomes ``request.user``.
#. ``can_join_channel`` must allow the channel, and, if ``CHECK_PERMISSIONS_ON_CONNECT`` is ``True``, the user must pass the permission checks.
#. ``_additional_connection_checks`` must return ``True``.
#. The ``WebSocketSession`` is created.

On ``disconnect``, the session is marked as not connected.

On any other route:

#. The body must be a JSON object that has a handler key.
#. A session for the ``Connectionid`` must exist, still be connected, and belong to the same API Gateway, otherwise the response is 400.
#. The handler method is chosen, as described below.
#. ``request.user`` is set to the session's user, if it has one.
#. The permission checks are made, and the response is 403 if the user fails them.
#. The handler runs.

If the handler returns nothing, the response is an empty JSON object. If it raises an exception, the exception is logged on the ``django_aws_api_gateway_websockets.views`` logger, an email is sent to the administrators if ``SEND_EXCEPTION_MAIL`` is ``True``, and the exception is raised again.

Choosing the handler
--------------------

The body of a message is a JSON object. The value of its ``handler`` key, which is ``handler_selection_key``, names the method to call. The ``action`` key, which is ``route_selection_key``, is read when ``handler`` does not name an allowed method. The code marks ``route_selection_key`` as deprecated. If the body has neither key, the response is 400.

.. code-block:: json

   {
     "handler": "chat_message",
     "message": "Hello"
   }

Only a method in ``ALLOWED_HANDLERS`` can be called, and a name that starts with an underscore never can. A name that is not allowed calls ``default``. This stops a client from calling any method on the view.

If you leave ``ALLOWED_HANDLERS`` empty, it is built for you from:

* ``default``;
* every name in ``ADDITIONAL_ALLOWED_HANDLERS``;
* every plain method defined on your own subclass, except the ones that ``WebSocketView`` itself defines.

.. versionchanged:: 4.1
   Before, every public callable on your subclass was in the list, including the hooks you override, such as ``can_join_channel``, ``get_channel_permission``, ``has_any_permission`` and ``connect``, and class attributes such as a model. A client could name any of them. Now only functions are included, and a name that ``WebSocketView`` defines is left out. ``default`` and ``change_channel`` are the exceptions: defining one on your subclass still lets clients call it.

.. important::

   A method that your subclass only inherits is not in that list. This includes ``change_channel``. To let clients call it, name it in ``ADDITIONAL_ALLOWED_HANDLERS``, or define it on your subclass, even if it only calls ``super()``.

.. warning::

   Every public method you add to a view without ``ALLOWED_HANDLERS`` becomes callable by every connected client. Set ``ALLOWED_HANDLERS``. ``python manage.py check --deploy`` reports each routed view that does not (``django_aws_api_gateway_websockets.W005``).

If you set ``ALLOWED_HANDLERS`` yourself, it is used exactly as you give it.

Responses
---------

.. list-table::
   :header-rows: 1
   :widths: 12 28 60

   * - Status
     - Method that answers
     - Cause
   * - 400
     - ``missing_headers``
     - A required header is missing, or the gateway is not registered.
   * - 400
     - ``invalid_useragent``
     - ``CHECK_CONNECT_USERAGENT`` is ``True`` and the ``$connect`` request does not carry the API Gateway ``User-Agent``.
   * - 400
     - ``handler_selection_key_missing``
     - A message has no ``handler`` or ``action`` key.
   * - 400
     - ``session_not_found``
     - A message or disconnect names a session that is unknown, or already closed.
   * - 400
     - none
     - ``$connect`` failed a check: the rate limit, a header, the host, the origin, the channel or the token.
   * - 403
     - ``invalid_gateway_secret``
     - The gateway secret header is missing or wrong.
   * - 403
     - ``permission_denied``
     - The user lacks a required permission, or ``can_join_channel`` refused the channel.
   * - 405
     - Django
     - The HTTP method is not allowed.

The response goes to API Gateway and not to the client, and it gives only a short reason. Set ``debug = True`` on the view to collect the full reason for each failure in ``debug_log``.

Class attributes
----------------

Set these on your subclass. The settings page describes each in more detail: :doc:`settings`.

.. list-table::
   :header-rows: 1
   :widths: 34 22 44

   * - Attribute
     - Default
     - Purpose
   * - ``ALLOWED_HANDLERS``
     - empty
     - The methods a client can call. Empty means the list described above.
   * - ``ADDITIONAL_ALLOWED_HANDLERS``
     - empty
     - Names to add to the built list, such as inherited methods.
   * - ``handler_selection_key``
     - ``"handler"``
     - The body key that names the handler.
   * - ``route_selection_key``
     - ``"action"``
     - The deprecated second body key that names the handler.
   * - ``USE_WS_TOKEN``
     - ``True``
     - Require a one-time token on ``$connect``.
   * - ``permissions_required``
     - empty
     - The user needs any one of these Django permissions.
   * - ``all_permissions_required``
     - empty
     - The user needs all of these Django permissions. When it is set, ``permissions_required`` is ignored.
   * - ``CHECK_PERMISSIONS_ON_CONNECT``
     - ``False``
     - Apply the two permission lists to ``$connect`` too. They apply to messages either way.
   * - ``ALLOW_UNLISTED_CHANNELS``
     - ``True``
     - Whether a channel with no ``ChannelPermission`` row can be joined.
   * - ``MAX_CHANNEL_NAME_LENGTH``
     - ``128``
     - The longest channel name. It must not exceed the database column.
   * - ``CHANNEL_NAME_PATTERN``
     - letters, numbers, ``_``, ``-``
     - The pattern a channel name must match.
   * - ``MAX_BODY_SIZE``
     - 128 KB
     - A larger body is ignored and treated as empty.
   * - ``RATE_LIMIT_ENABLED``
     - ``True``
     - Limit the connection attempts from one address or user.
   * - ``RATE_LIMIT_MAX_ATTEMPTS``
     - from ``WEBSOCKETS``
     - Attempts allowed in the window. ``0`` means use the setting.
   * - ``RATE_LIMIT_WINDOW_MINUTES``
     - from ``WEBSOCKETS``
     - The window, in minutes. ``0`` means use the setting.
   * - ``aws_api_gateway_id``
     - ``None``
     - Accept requests from this API Gateway only.
   * - ``CHECK_CONNECT_USERAGENT``
     - ``False``
     - Require the API Gateway ``User-Agent`` on ``$connect``. See :ref:`useragent-check`.
   * - ``expected_useragent_prefix``
     - ``"AmazonAPIGateway_"``
     - The start of the ``$connect`` ``User-Agent``, when ``CHECK_CONNECT_USERAGENT`` is ``True``.
   * - ``required_headers``
     - see the code
     - Headers every request must have.
   * - ``additional_required_headers``
     - see the code
     - More headers every request must have. Relax these in development only.
   * - ``required_connection_headers``
     - see the code
     - Headers the ``$connect`` request must also have.
   * - ``SEND_EXCEPTION_MAIL``
     - ``True``
     - Email the administrators when a handler raises an exception.
   * - ``EXCEPTION_MAIL_INTERVAL``
     - ``60``
     - At most one exception email for each view and exception type in this many seconds, for each process. ``0`` sends one every time.
   * - ``debug``
     - ``False``
     - Collect the reason for each failure in ``debug_log``.

Methods you can override
------------------------

``default(request, *args, **kwargs)``
   Called when a message names no allowed handler. It raises ``NotImplementedError`` until you override it, so every view needs one.

``can_join_channel(request, channel_name)``
   Return ``False`` to refuse a channel, on ``$connect`` and in ``change_channel``. Call ``super()`` to keep the stored rules. See :doc:`channel_permissions`.

``get_channel_permission(channel_name)``
   Return the ``ChannelPermission`` for a channel, or ``None``. Override it to cache the lookup or build a rule from the name.

``change_channel(request, *args, **kwargs)``
   Moves the session to the channel in ``body["channel"]``. It returns ``None`` when it works and a 400 or 403 response when it does not, so return that response from your override.

``connect(request, *args, **kwargs)`` and ``disconnect(request, *args, **kwargs)``
   The two lifecycle routes. Override them only to add to what they do, and call ``super()``, because they hold the checks above.

``_additional_connection_checks(request, *args, **kwargs)``
   Return ``(True, "")`` to allow a connection, or ``(False, "reason")`` to refuse it with a 400 response. Use it for checks of your own, such as a client certificate. The name starts with an underscore because it is a hook and not a handler, so a client can never call it.

``has_any_permission(request)`` and ``has_all_permission(request)``
   The permission checks. Override them to change how permissions are tested.

``missing_headers``, ``invalid_useragent``, ``session_not_found``, ``permission_denied``, ``invalid_gateway_secret``, ``handler_selection_key_missing``
   Each returns the response for one failure, and each can be overridden to change the response.

What a handler can use
----------------------

Inside a handler method:

``request.user``
   The session's user, or an anonymous user if the connection had none.

``self.body``
   The message, as a dictionary. It is empty when the body was not a JSON object, was too large, or was not valid JSON.

``self.websocket_session``
   The ``WebSocketSession`` of the connection. To change it, write only the fields you change, with ``save(update_fields=[...])``. See :doc:`message_patterns`.

``self.api_gateway``
   The ``ApiGateway`` record that made the request.

``self.kwargs["route"]``
   The route from the URL.

To send a message back, use ``self.websocket_session.send_message(...)`` for the connection, or ``WebSocketSession.objects.filter(...).send_message(...)`` for a channel. See :doc:`message_patterns`.

See also
========

* :doc:`security`, for what each check protects against;
* :doc:`permissions` and :doc:`channel_permissions`, for who may connect and join channels;
* :doc:`websocket_tokens` and :doc:`gateway_secret`, for the token and the gateway secret;
* :doc:`rate_limiting`, for the connection limits;
* :doc:`example`, for a complete chat view.
