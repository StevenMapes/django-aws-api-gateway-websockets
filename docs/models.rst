######
Models
######

The package stores its state in a few Django models, all in ``django_aws_api_gateway_websockets.models``. This page describes each model, its fields and the methods you are likely to call. For the generated signatures, see :doc:`api/index`. For the Django Admin pages, see :doc:`admin`.

Apply the migrations after installing or upgrading the package:

.. code-block:: console

   python manage.py migrate

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Model
     - Holds
   * - ``ApiGateway``
     - An AWS API Gateway WebSocket API, and how far creating it has got.
   * - ``ApiGatewayAdditionalRoute``
     - An extra route key on an API Gateway, and the URL it calls.
   * - ``WebSocketSession``
     - One WebSocket connection, its channel and its user.
   * - ``WebSocketToken``
     - A one-time token that lets a browser connect.
   * - ``ConnectionRateLimit``
     - One connection attempt, used to limit attempts.
   * - ``ChannelPermission``
     - Who may join a channel. See :doc:`channel_permissions`.
   * - ``ChannelPermissionRule``
     - One set of permissions that admits a user to a channel.

``ApiGateway``
==============

Describes an API Gateway WebSocket API. Creating the record does nothing in AWS. The ``Create API Gateway`` admin action, the ``createApiGateway`` command, or ``create_gateway()`` creates the API. See :doc:`api_gateway_setup`.

Fields you set
--------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``api_name``
     - A unique name, of letters, numbers, spaces, hyphens and underscores.
   * - ``api_description``
     - A description, sent to AWS.
   * - ``target_base_endpoint``
     - The URL of your Django view, up to but not including the route, such as ``https://www.example.com/ws/``. A trailing ``/`` is added if it is missing. It is required to create the API.
   * - ``default_channel_name``
     - The channel a connection joins when it names none.
   * - ``domain_name``
     - A custom domain for the API, such as ``ws.example.com``.
   * - ``certificate_arn``
     - The ARN of the AWS Certificate Manager certificate for the custom domain.
   * - ``hosted_zone_id``
     - The Route 53 hosted zone for the domain.
   * - ``api_key_selection_expression``
     - The API key expression. The default is ``$request.header.x-api-key``.
   * - ``route_selection_expression``
     - How API Gateway picks a route from a message. The default is ``$request.body.action``.
   * - ``route_key``
     - The route that receives messages that match no other. The default is ``$default``.
   * - ``stage_name`` and ``stage_description``
     - The stage to deploy to, ``production`` by default, and its description.
   * - ``tags``
     - A JSON object of tags.

Values from AWS
---------------

These are filled in as the API is created. Do not edit them, apart from ``provisioning_status``.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``api_id`` and ``api_endpoint``
     - The ID and the endpoint of the API.
   * - ``deployment_id``
     - The latest deployment. It is empty until the API has been deployed.
   * - ``api_gateway_domain_name``
     - The value to point your DNS ``CNAME`` record at.
   * - ``api_mapping_id``
     - The ID of the mapping between the custom domain and the API.
   * - ``api_created`` and ``custom_domain_created``
     - ``True`` as soon as the API, or the custom domain, exists in AWS, even if later steps have not finished.
   * - ``provisioning_status``
     - How far provisioning has got: ``pending``, ``creating``, ``api_created``, ``routes_created``, ``deployed``, ``domain_created`` or ``mapped``. See :doc:`admin`.
   * - ``last_error``
     - The kind of error, and the AWS error code, that stopped the last step. It is empty after a step succeeds.
   * - ``created_on`` and ``updated_on``
     - When the record was created and last saved.

Methods and properties
----------------------

``create_gateway()``
   Creates the API, its routes, the stage and the deployment. Each step is saved as it succeeds, so running it again after a failure carries on from the last step that worked. Returns ``True`` when it creates the gateway and ``False`` when it was already complete. Raises ``ValueError`` if ``target_base_endpoint`` is not set.

``create_custom_domain()``
   Creates the custom domain and maps it to the stage, as two separate steps. It needs a complete API and a ``certificate_arn``.

``deploy_api(client)``
   Creates a deployment and sets ``deployment_id`` in memory. Save the record to keep it.

``sync_to_aws(client=None, fields=None)`` and ``sync_from_aws(client=None)``
   Write the local values to the deployed API, or read the API into the local records. Each returns a list of sentences that describe what changed. See :ref:`api-gateway-auto-sync`.

``is_deployed``
   ``True`` once the API exists in AWS and has been deployed.

``needs_api_creation`` and ``needs_custom_domain``
   ``True`` while the API is not complete, or while the domain or its mapping is not complete.

``effective_provisioning_status``
   The status, allowing for records that predate it. A record still ``pending`` with ``api_created`` set is treated as complete.

``save(push_to_aws=None)``
   Validates the whole record, and adds the trailing ``/`` to ``target_base_endpoint``. If the API is deployed and a field that AWS holds has changed, the change is also sent to AWS. A save with ``update_fields`` writes only those columns, skips validation and never calls AWS. See :doc:`settings` for ``push_changes_to_aws``.

``ApiGatewayAdditionalRoute``
=============================

An extra route key on an ``ApiGateway``, and the Django URL that API Gateway calls for it. A ``route_key`` is unique within its API Gateway.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``api_gateway``
     - The ``ApiGateway`` this route belongs to.
   * - ``name``
     - A description of the route.
   * - ``route_key``
     - The route key that clients send.
   * - ``integration_url``
     - The URL API Gateway calls for this route.
   * - ``deployed``
     - ``True`` once the route exists in AWS.
   * - ``route_id`` and ``integration_id``
     - The AWS IDs of the route and its integration. A route saved before these existed has none, and is found by its route key.

Saving a new route on an API Gateway that has been deployed creates it in AWS. Editing or deleting a deployed route changes AWS as well, unless ``push_changes_to_aws`` is ``False``. Pass ``push_to_aws=False`` to ``save()`` or ``delete()`` to skip AWS for one call. See :ref:`api-gateway-auto-sync`.

``WebSocketSession``
====================

One WebSocket connection. The connect route creates it, and the disconnect route marks it as not connected.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``connection_id``
     - The AWS connection ID. It is unique.
   * - ``channel_name``
     - The channel the connection is in. It can be empty.
   * - ``user``
     - The user the connection belongs to, or ``None`` for an anonymous connection. The reverse name is ``websocket_sessions``.
   * - ``connected``
     - ``True`` while the connection is open.
   * - ``api_gateway``
     - The ``ApiGateway`` that the connection came through. The reverse name is ``sessions``.
   * - ``request_count``
     - The number of messages the connection has sent, plus one.
   * - ``created_on`` and ``updated_on``
     - When the record was created and last saved.

Sending messages
----------------

Send to one connection:

.. code-block:: python

   session.send_message({"type": "notification", "message": "Hello"})

Send to every connected session in a queryset:

.. code-block:: python

   WebSocketSession.objects.filter(channel_name="support").send_message(
       {"type": "notification", "message": "Hello"}
   )

On an instance, ``send_message(data)`` returns the AWS response. It reads the two columns it needs from the session's API Gateway, one query, unless you loaded the gateway with ``select_related("api_gateway")``, when it reads none. It raises ``ValueError`` if the JSON is over 128 KB or the session has no API Gateway, and raises the AWS error if AWS refuses. If the client has gone away, it marks the session as not connected and returns ``None``.

On a queryset, ``send_message(data, max_workers=10)`` posts to the connected sessions at the same time, up to ``max_workers`` at once for each API Gateway. A recipient that fails does not stop the others: the failure is logged on the ``django_aws_api_gateway_websockets.models`` logger. Sessions whose client has gone away are marked as not connected in one query. Sessions with no API Gateway are skipped, with one warning that gives their number, and stay marked as connected. A session has none when the view uses a fixed ``aws_api_gateway_id`` and you have no ``ApiGateway`` records. The return value is a list of the AWS responses for the posts that worked. The call waits for every post, so send from a background task if the channel is large. See :doc:`message_patterns`.

To send the same message to many sessions, use the queryset form. Calling ``send_message`` on each session in a loop makes one HTTP call after another and, without ``select_related("api_gateway")``, one query for each session:

.. code-block:: python

   # Slow: one query and one request at a time
   for session in WebSocketSession.objects.filter(channel_name="support"):
       session.send_message(data)

   # Fast: one query, and concurrent requests
   WebSocketSession.objects.filter(channel_name="support").send_message(data)

Deleting an ``ApiGateway`` marks its sessions as not connected before it clears their ``api_gateway``, because they could no longer be sent to.

``WebSocketToken``
==================

A one-time token that the connect route accepts when ``USE_WS_TOKEN`` is ``True``. See :doc:`websocket_tokens`.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``token``
     - A random 64-character hexadecimal value. It is unique.
   * - ``user``
     - The user who asked for the token. The reverse name is ``websocket_tokens``.
   * - ``session_key``
     - A keyed hash of the Django session key that asked for the token, never the key itself.
   * - ``created_at``
     - When the token was created.
   * - ``used``
     - ``True`` once the token has been spent.

``WebSocketToken.generate_token(user, session_key)``
   Creates a token. Pass the real session key, and it is hashed for you.

``WebSocketToken.validate_and_consume(token_value, session_key, max_age_seconds=60)``
   Returns the user and marks the token as used, if it is unused, young enough and was made for that session. Otherwise it returns ``None``. The view passes ``token_expiry_seconds`` as the age.

``WebSocketToken.check_rate_limit(user, max_tokens_per_minute=10)``
   ``True`` if the user may have another token.

``WebSocketToken.cleanup_expired(max_age_seconds=300)``
   Deletes tokens older than that, used or not. The ``cleanupWebSocketTokens`` command calls it.

``ConnectionRateLimit``
=======================

One connection attempt, recorded so that attempts can be limited. See :doc:`rate_limiting`.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``ip_address``
     - The address the attempt came from.
   * - ``user``
     - The user, if there was one. The reverse name is ``connection_attempts``.
   * - ``attempt_time``
     - When the attempt was made.
   * - ``successful``
     - Whether the connection was accepted.

``ConnectionRateLimit.check_rate_limit(ip_address, user=None, max_attempts=20, window_minutes=5)``
   Returns ``(is_allowed, attempts)``. The limit applies to the address and, if there is one, to the user. ``WebSocketView`` always passes the window from its settings, which is 1 minute by default.

``ConnectionRateLimit.record_attempt(ip_address, user=None, successful=False)``
   Records an attempt.

``ConnectionRateLimit.cleanup_old_records(days=7)``
   Deletes records older than that.

``ChannelPermission`` and ``ChannelPermissionRule``
===================================================

``ChannelPermission`` says who may join one channel: everyone, super admins only, staff only, or users who hold Django permissions. A ``ChannelPermissionRule`` is one set of permissions the user must all hold, and a channel can have several rules. See :doc:`channel_permissions` for how they are combined and enforced.

``ChannelPermission.for_channel(channel_name)``
   Returns the row for a channel, or ``None``.

``ChannelPermission.allows(user)``
   ``True`` if the user may join the channel.

Helper functions
================

These are also in ``django_aws_api_gateway_websockets.models``.

``get_boto3_client(service="apigatewayv2", **kwargs)``
   Returns the boto3 client the package uses. It uses a named profile if ``AWS_IAM_PROFILE`` is set, then the keys in ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY`` if both are set, and otherwise the credentials of the machine, such as an IAM role. With keys or a role it needs a region. With a named profile, the region comes from the profile. Extra keyword arguments go to boto3. The client has a 5 second connect timeout, a 20 second read timeout and up to 3 attempts, unless you pass your own ``config``. It is built once for each process and set of arguments, and reused, so a web server that runs many workers builds one per worker. boto3 clients can be shared between threads. A role's temporary credentials refresh on their own.

``clear_boto3_client_cache()``
   Forgets the cached clients. Call it after changing the AWS credential settings in a running process. Changing a setting with ``override_settings`` needs no call, because the settings are part of the cache key.

``get_region_name()``
   Returns ``AWS_GATEWAY_REGION_NAME``, or ``AWS_REGION_NAME`` if that is not set, and raises ``RuntimeError`` if neither is.

``serialise_message(data)``
   Returns ``data`` as a JSON string, and raises ``ValueError`` if it is over 128 KB, which is the AWS limit.

   .. versionchanged:: 4.1.1
      Uses :class:`~django.core.serializers.json.DjangoJSONEncoder`, so lazy translation strings, dates, times, ``Decimal`` and ``UUID`` values serialise as text.

``hash_session_key(session_key)``
   Returns the keyed hash that ``WebSocketToken`` stores. If you create a token row yourself, store this and not the key.

``get_gateway_secrets()`` and ``integration_request_parameters()``
   Read the gateway secret setting, and build the request parameters for an integration, which include the secret header when one is set. See :doc:`gateway_secret`.

Database tables
===============

Each model uses a table named after the app and the model, such as ``django_aws_api_gateway_websockets_websocketsession``.

See also
========

* :doc:`admin`, for the admin pages and actions;
* :doc:`concepts`, for how the models fit together;
* :doc:`cleanup`, for removing old sessions, tokens and rate limit records.
