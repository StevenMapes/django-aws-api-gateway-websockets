Changelog
=========

:tocdepth: 1

5.* - Future Release - Breaking changes
------------------------------------------------

-  The ``route_selection_key`` property has been removed as per the
   warning in version 2.0.0. Please update your integration.
- This change has not happened yet so treat it as a warning

4.1.0 - Unreleased - Security updated
-------------------------------------

Added
~~~~~

-  Added the ``django_aws_api_gateway_websockets.E002`` system check, which reports a ``WEBSOCKETS`` value that is not a whole number of 1 or more (or, for ``push_changes_to_aws``, not ``True`` or ``False``), the ``W002`` check, which warns about an unknown ``WEBSOCKETS`` key, and the ``W003`` check, which warns under ``check --deploy`` when no AWS region is set.
-  Added the ``provisioning_status`` and ``last_error`` fields to ``ApiGateway``, which record how far creating the API, its custom domain and the mapping has got, and the error that stopped the last step. The migration only adds the two columns, and needs no AWS change.
-  Added an optional gateway secret, set with ``WEBSOCKETS["gateway_secret"]``, that API Gateway sends in the ``X-Ws-Gateway-Secret`` header and that ``WebSocketView`` requires before it handles any request. It is off by default, so nothing changes until you set it. See :doc:`gateway_secret`.
-  Added the ``updateApiGatewayIntegrations`` management command, which adds, changes or removes the gateway secret header on the integrations of API Gateways that are already deployed. You must run it before you set the secret on the web processes of an existing deployment.
-  Added the ``django_aws_api_gateway_websockets.E001`` system check, which reports an invalid gateway secret, and the ``django_aws_api_gateway_websockets.W001`` check, which warns under ``check --deploy`` when no secret is set.
-  Added the ``django_aws_api_gateway_websockets.W005`` system check, which warns under ``check --deploy`` for each routed ``WebSocketView`` that has no ``ALLOWED_HANDLERS`` and defines methods a client could call.
-  Added ``WebSocketView.EXCEPTION_MAIL_INTERVAL``, which limits the exception emails to one for each view and exception type every 60 seconds in each process. Set it to ``0`` to email every time.
-  Added the ``allowed_integration_hosts`` key to the ``WEBSOCKETS`` setting. When it is set, the host of an API gateway's ``target_base_endpoint`` and of an additional route's ``integration_url`` must be in the list, or the save is refused. See :ref:`admin-integration-permissions`.
-  Added the ``django_aws_api_gateway_websockets.W004`` system check, which warns under ``check --deploy`` for each routed ``WebSocketView`` that has ``ALLOW_UNLISTED_CHANNELS = True``. See :ref:`channel-permissions-unlisted`.
-  Added the ``ChannelPermission`` and ``ChannelPermissionRule`` models and a Django Admin page, so a channel can be limited to super admins, staff, or users who hold Django permissions in any combination of AND and OR. See :doc:`channel_permissions`.
-  Added ``WebSocketView.can_join_channel(request, channel_name)`` and ``WebSocketView.get_channel_permission(channel_name)``, called on connect and by ``change_channel``, so a view can refuse a channel. A refused request gets a 403 response and no session is created.
-  Added ``WebSocketView.ALLOW_UNLISTED_CHANNELS`` and ``WebSocketView.CHECK_PERMISSIONS_ON_CONNECT``. Both default to the previous behaviour: channels without a rule are open, and ``permissions_required`` applies only to messages. Both defaults are planned to change in a future major version.

-  Added syncing of a deployed API Gateway with AWS. Saving an ``ApiGateway`` or ``ApiGatewayAdditionalRoute`` that is already deployed now updates AWS: adding, removing and changing the URL or key of an additional route, and changing the name, description, base URL or stage description of the API Gateway. See :ref:`api-gateway-auto-sync`.
-  Added the ``push_changes_to_aws`` key to the ``WEBSOCKETS`` setting. It is ``True`` by default, which keeps the syncing described above. Set it to ``False`` to go back to the earlier behaviour, where editing or deleting a deployed ``ApiGateway`` or ``ApiGatewayAdditionalRoute`` changes only the local record. A new additional route is still created in AWS when it is saved, and the ``Sync to AWS`` and ``Sync from AWS`` actions still work. A ``push_to_aws`` argument on a single ``save()`` or ``delete()`` overrides the setting.
-  Added the ``Sync to AWS`` and ``Sync from AWS`` admin actions on the API Gateway list page, which write the local records to AWS and read AWS into the local records, and report what changed.
-  Added the ``ApiGateway.sync_to_aws()`` and ``ApiGateway.sync_from_aws()`` methods, the ``ApiGatewaySyncError`` exception, and a ``push_to_aws`` argument on ``save()`` and ``delete()`` to choose whether AWS is called.
-  Added the ``deployment_id`` and ``api_created`` fields to the API Gateway admin page, and ``deployment_id`` to its list page. Both are read-only.
-  Added the ``route_id`` and ``integration_id`` fields to ``ApiGatewayAdditionalRoute``, which store the AWS IDs of its route and integration. The migration only adds the two columns, and needs no AWS change.
-  Added the ``session_key_hash`` and ``auth_hash`` fields to ``WebSocketSession``, which hold keyed hashes that tie a session to a login. The migration only adds the two columns, and needs no AWS change.

Changed
~~~~~~~

-  Changed the default age of the ``cleanupWebSocketTokens`` command to 5 minutes, or ``token_expiry_seconds`` if that is longer, so it never deletes a token that is still valid.
-  Changed the ``createApiGateway`` and ``createCustomDomain`` commands to raise a command error, not ``DoesNotExist``, for a gateway that has nothing left to do, and to resume a gateway that stopped part way.
-  Changed ``ApiGateway.save()`` to skip validation when it is called with ``update_fields``, so recording progress cannot fail because an unrelated field is invalid. A full save still validates the whole record.
-  Changed ``WebSocketSession.objects.filter(...).send_message()`` to post to recipients concurrently, with a new optional ``max_workers`` argument that defaults to 10.
-  Changed ``WebSocketSession.objects.filter(...).send_message()`` to log a warning and carry on when a recipient fails, instead of raising and skipping the remaining recipients.
-  Changed ``WebSocketSession.objects.filter(...).send_message()`` to mark all disconnected sessions with a single query.
-  Changed ``WebSocketSession.objects.filter(...).send_message()`` to use a 5 second connect timeout, a 10 second read timeout and up to 3 attempts for each post.
-  Changed the chat examples to broadcast from a background task after the transaction commits.
-  Changed ``WebSocketView`` to answer a request body that is not a JSON object, or that is not valid JSON or UTF-8, as an empty body instead of raising an exception.
-  Changed ``WebSocketView`` to answer an invalid channel on connect with a 400 response before the one-time token is used, and to count it as a failed connection attempt.
-  Changed the ``change_channel`` handler to answer a missing or invalid channel with a 400 response, using the same rules as the channel on connect.
-  Changed the ``$disconnect`` route to answer an unknown connection with a 400 response instead of raising an exception.

-  Changed deleting an ``ApiGatewayAdditionalRoute`` to delete its route and integration in AWS when its API Gateway is deployed. The credentials used by Django need the ``apigateway:DELETE`` permission, which :doc:`aws_iam_setup` now lists.

Security
~~~~~~~~

-  Added ``WebSocketView.CHECK_CONNECT_USERAGENT``, which makes the ``$connect`` route require the exact User-Agent ``AmazonAPIGateway_`` followed by the API ID, and answer anything else with a 400 response. It is ``False`` by default, because some APIs forward the client's own User-Agent on ``$connect``, and the check then refuses every browser. Turn it on only if your API sends the gateway User-Agent. See :ref:`useragent-check`.
-  Changed the ``Create API Gateway`` and ``Create Custom Domain`` admin actions to require the change permission on API gateways, so a user who can only view them no longer sees the actions or can run them. Users who run these actions without the change permission must be given it.
-  Changed the API Gateway documentation to say that the API ID and header checks do not prove a request came from API Gateway, and to point to the gateway secret.
-  Changed ``WebSocketToken.session_key`` to store a keyed hash of the Django session key instead of the key, and removed it from the token admin page. The column is now 64 characters, and a new migration deletes existing tokens, which are single use and valid for about a minute. Users with a token in flight at the time of the upgrade must request a new one.
-  Changed the ``WebSocketSession`` admin page to be read-only, so staff can no longer attach a live connection to another user.
-  Changed ``WebSocketView`` to reject a ``$connect`` request whose ``Connectionid`` header is not a valid AWS connection ID.
-  Changed ``WebSocketView`` to accept a ``Connectionid`` only for a session that is still connected and belongs to the API Gateway making the request, so a closed session can no longer be used to act as its user.
-  Changed ``WebSocketView`` to answer a message for an unknown or closed session with a 400 response, where it previously raised an exception.
-  Changed the ``$disconnect`` route to close only a session that belongs to the API Gateway that sent the request.
-  Changed the handler list that ``WebSocketView`` builds when ``ALLOWED_HANDLERS`` is empty to leave out the names ``WebSocketView`` defines, such as ``can_join_channel`` and ``connect``, and anything that is not a plain function. ``default`` and ``change_channel`` can still be defined on a subclass. A client could name the other methods before.
-  Changed the ``$connect`` origin check to parse the ``Origin`` header and compare its host name with the ``Host`` header, so an origin that only contains the host, such as ``https://www.example.com.attacker.net``, is refused. A sub-domain of the host is still accepted.
-  Changed ``ApiGatewayAdditionalRoute.save()`` to validate the record with ``full_clean()``, as ``ApiGateway.save()`` does, unless ``update_fields`` is given.
-  Changed the connection rate limit check to count the IP address and the user in one query instead of two.
-  Changed recording a connection attempt to delete up to 500 attempts older than 7 days about once in every 100 attempts, so the table stays bounded when ``cleanupWebSocketTokens`` is not scheduled.
-  Changed ``WebSocketSession.send_message()`` to read only the API ID and stage name of the session's API Gateway, and to read nothing if the gateway is already loaded.
-  Changed ``WebSocketView`` to load a session once for each message, with its user, and to count the request with one ``UPDATE`` instead of locking the row, so a message costs three queries instead of five and messages from one connection no longer wait for each other.
-  Changed ``WebSocketSession.send_message()`` to raise a ``ValueError`` that names the session when it has no API Gateway, instead of an ``AttributeError``, and the queryset ``send_message()`` to skip such sessions with one warning, instead of posting to an endpoint called ``None``.
-  Changed deleting an ``ApiGateway`` to mark its sessions as not connected, because they can no longer be sent to.
-  Changed saving a deployed ``ApiGateway``, editing or deleting an ``ApiGatewayAdditionalRoute``, and deleting routes with a queryset to call AWS when the open transaction commits, so the call holds no database locks and a rolled back change never reaches AWS. With no transaction open the call still runs at once. Adding a route is unchanged. See :ref:`api-gateway-auto-sync-transactions`.
-  Changed ``get_boto3_client()`` to use a 5 second connect timeout, a 20 second read timeout and up to 3 attempts unless you pass your own ``config``, and to build each client once for each process and reuse it. Added ``clear_boto3_client_cache()``.
-  Changed the API Gateway admin pages to show an AWS failure that happens as a change commits as a message, as they did for a failure during the save.
-  Changed ``WebSocketView`` to close a session, and answer its message with a 400 response, when the user has been deactivated or has changed their password since the connection was made, and to close the sessions opened under a Django session when its user logs out. See :doc:`security`.

Fixed
~~~~~

-  Fixed two requests to create the same API Gateway both creating an API in AWS, and one API being left with nothing pointing to it. A run now claims the record first, and a second run is refused while the status shows ``Creating``. See :doc:`admin`.
-  Fixed deleting an ``ApiGateway`` from a queryset, the admin ``Delete selected`` action or a cascade deleting its routes in AWS. Only deleting a route now changes AWS, and the admin reports an AWS failure on a bulk delete instead of showing an error page.
-  Fixed changes to the ``route_key`` or ``integration_url`` of a deployed additional route being saved locally but never sent to AWS.
-  Fixed ``token_expiry_seconds`` only changing the ``expires_in`` value sent to the client. The connect route now refuses a token older than the configured time, where it always used 60 seconds before. Projects that set another value now get the behaviour they configured.
-  Fixed ``WebSocketView`` failing to start when ``WEBSOCKETS`` is ``None``.
-  Fixed saving an additional route that was created with its API Gateway failing with a conflict, and leaving an unused integration in AWS, because the route was never marked as deployed.
-  Fixed the deployment ID of an API Gateway being lost when an additional route was deployed to an API Gateway that was already deployed.
-  Fixed a half-built API Gateway looking complete, and being impossible to finish, after a failure while creating its routes, stage or custom domain mapping. Each step is now saved as it succeeds, a second run continues from the last step that worked, and the admin shows the status and the error. Records created before this version, and records registered by hand for an existing API, are treated as complete.
-  Fixed the API ID being lost, and the API left in AWS with nothing pointing to it, when the record failed validation after the API had been created. The record is now validated before anything is created in AWS.
-  Fixed ``change_channel`` resetting ``request_count``, and the ``$disconnect`` route and ``WebSocketSession.send_message()`` overwriting other changes to the session, by making them write only the fields they change.
-  Fixed the User-Agent check being applied to messages and ``$disconnect``, where the client's own User-Agent is sent. A view with ``aws_api_gateway_id`` set no longer refuses every message and disconnect, and a view without it no longer requires the gateway User-Agent on them. The check now applies to ``$connect`` only, and only when ``CHECK_CONNECT_USERAGENT`` is ``True``.
-  Fixed the ``Create API Gateway`` admin action reporting ``already created`` after it had created the gateway.
-  Fixed the ``Create API Gateway`` admin action and ``ApiGateway.create_gateway()`` failing with an unclear error when ``target_base_endpoint`` is not set. They now report that the field is required before calling AWS.
-  Fixed saving an ``ApiGateway`` without a ``target_base_endpoint`` raising a ``TypeError``.
-  Fixed the API Gateway ``Target`` containing a double slash.
-  Fixed searching the additional route admin page raising an error.
-  Fixed channel names of 129 to 191 characters being accepted and then failing at the database, by lowering the ``MAX_CHANNEL_NAME_LENGTH`` default from 191 to 128 to match the ``WebSocketSession.channel_name`` column.
-  Fixed ``WebSocketSession.objects.filter(...).send_message()`` posting every session through the first session's API Gateway when the queryset spans more than one gateway.
-  Fixed ``WebSocketSession.objects.filter(...).send_message()`` accepting messages over the 128 KB AWS limit.

4.0.0 - 18th August 2026 - Dropped support for Django < 5.2 and Python < 3.10
-----------------------------------------------------------------------------
This release drops support for Django < 5.2. Python 3.10 is currently still supported but that
will be dropped from the test matrix and official support in the future.


3.1.1 - 10th June 2026 - Websocket error logging and mail_admin integration
---------------------------------------------------------------------------
If an exception is raised during the WebSocketView's dispatch method, then the exception will be written to the Python
logger and an email send via Django's mail_admins function. You can turn off the mail sending by setting the class
property SEND_EXCEPTION_MAIL to False. The exception is then raised again for backward compatibility.

Django Logger settings example

.. code-block:: python

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
            },
        },
        "loggers": {
            "django_aws_api_gateway_websockets": {
                "handlers": ["console"],
                "level": "ERROR",
                "propagate": False,
            },
        },
    }

3.1.0 - 10th June 2026 - Added Django Settings variables to control the WebsocketToken rate limit and expiry time
-----------------------------------------------------------------------------------------------------------------
Introduces a new settings.py dictionary for optionally controlling the rate limits for the token and the websocket
connections. All keys within the dictionary below are optional, and the values shown are the default values.

`token_rate_limit_per_minute` and `token_expiry_seconds` are used by the WebSocketTokenView that handles the CSRF
protected token generation endpoint

`rate_limit_max_attempts` and `rate_limit_window_minutes` are used by the WebSocketView object to allow project level
overrides of the default values. Previously you had to set the class properties on the subclass directly if you needed
this. You can still overload them in that manner if you wish to have different values per subclass

.. code-block:: python

    WEBSOCKETS = {
        "token_rate_limit_per_minute": 20,  # The number of tokens a user can request per minute
        "token_expiry_seconds": 60,  # The time, in seconds, that the token is valid for
        "rate_limit_max_attempts": 20,  # The number of connection attempts a user can make within the rate limit window
        "rate_limit_window_minutes": 1,  # The rate limit window for the connection attempts
    }

Adding Django 6.1a1 into the test suite

3.0.4 - 28th May 2026 - Renamed the WebSocketToken and RateLimit table names
----------------------------------------------------------------------------
This adds in the fix to work with Django 5.2 by removing the additional index.

3.0.3 - 28th May 2026 - Django 5.2 MySQL Index bug Fix (Yanked)
---------------------------------------------------------------
This adds in the fix to work with Django 5.2 by removing the additional index.

3.0.2 - 28th May 2026 - Django 5.2 MySQL Index bug Fix (Yanked)
---------------------------------------------------------------
Yanked as bug fix did not quite work


3.0.1 - 1st May 2026 - Security release - Breaking changes
----------------------------------------------------------
IMPORTANT: Do not us this version with Django < 6.0 due to an issue in the migration file where both db_index=True and
unique=True was set along with the composite index. This breaks on Django < 6 so jump to 3.0.2

Corrected the project changelog path within pyproject.toml to correct pypi

3.0.0 - 1st May 2026 - Security release - Breaking changes
----------------------------------------------------------
IMPORTANT: Do not us this version with Django < 6.0 due to an issue in the migration file where both db_index=True and
unique=True was set along with the composite index. This breaks on Django < 6 so jump to 3.0.2

This is a major release that introduces a number of security improvements and
breaking changes.

Ensure you run migrations after updating to this version.

To enable backward compatibility with previous versions, edit your subclasses of
``WebSocketView`` and set these class properties to ``False``:

.. code-block:: python

   USE_WS_TOKEN = False
   RATE_LIMIT_ENABLED = False

This disables the requirement to use WebSocket tokens and disables rate
limiting.

Critical security fixes
~~~~~~~~~~~~~~~~~~~~~~~

-  Added ``ALLOWED_HANDLERS`` enforcement, replacing dynamic method
   invocation with strict whitelist validation.
-  Added ``ALLOWED_HANDLERS`` so users can control which methods are
   exposed to the client.
-  By default, methods defined within the current class are exposed.
   To restrict this, set ``ALLOWED_HANDLERS`` to the list of methods you
   want to expose to end users.
-  Private methods starting with ``_`` are blocked.
-  Prevents arbitrary method invocation attacks.
-  Strengthened connection ID validation with improved regular expression
   validation and length checks.
-  Added XSS prevention for debug output. Debug output is now HTML-escaped
   and length-limited.

High priority security improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Added CSRF protection for WebSocket connections using the new
   ``WebSocketToken`` model.
-  Added ``WebSocketTokenView`` to generate time-limited tokens.
-  Tokens are single-use and session-bound.
-  Added ``USE_WS_TOKEN`` configuration.
-  Added rate limiting using the new ``ConnectionRateLimit`` model.
-  Added IP-based and user-based connection attempt tracking.
-  Added rate limiting configuration via ``RATE_LIMIT_MAX_ATTEMPTS`` and
   ``RATE_LIMIT_WINDOW_MINUTES``.
-  Added ``RATE_LIMIT_ENABLED`` to disable rate limiting where required.
-  Added input validation to ``ApiGateway`` model fields.
-  Added domain name format validation.
-  Added API name character restrictions.
-  Added URL validation for endpoints.

Medium priority security improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Missing headers no longer return the headers that were missing unless
   debug mode is enabled.
-  Reduced information disclosure with more generic production error
   messages.
-  Added enhanced message size validation before sending to AWS.
-  Added audit logging for administrative actions.
-  Added channel name validation for length and format.
-  Channel names are now limited to 191 characters.

New management commands
~~~~~~~~~~~~~~~~~~~~~~~

-  Added ``cleanupWebSocketTokens`` to clean up expired tokens and old rate
   limit records.
-  Added ``--token-age`` option to control the number of seconds before
   tokens are deleted. The default is ``300``.
-  Added ``--rate-limit-age`` option to control the number of days before
   rate limit records are deleted. The default is ``7``.

New models
~~~~~~~~~~

-  Added ``WebSocketToken`` for one-time use CSRF protection tokens.
-  Added ``ConnectionRateLimit`` for connection attempt rate limiting.

New methods
~~~~~~~~~~~

- Added ``change_channel`` method to the ``WebSocketView`` to use to change between channels


Recommendations
~~~~~~~~~~~~~~~

-  Enable ``USE_WS_TOKEN = True`` for CSRF protection.
-  Run ``cleanupWebSocketTokens`` via cron or Celery every 5 to 15 minutes.
-  Review and customise ``ALLOWED_HANDLERS`` for your views.
-  Configure rate limiting thresholds based on your usage patterns.
-  Enable audit logging in production.

2.2.2 - 26th March 2026
-----------------------

-  Dropped ``Connection`` from the default
   ``additional_required_headers`` list as it is no longer always coming
   through.
-  Issue found with a combination of AWS ALB, Python 3.14, Django 6, and
   Nginx 1.29.7.

2.2.1 - 18th March 2026
-----------------------

-  Added support for Python 3.15.

2.2.0 - 23rd February 2026
--------------------------

-  Updated ``AppChannelWebSocketMixin`` so that child classes can now set
   the ``app_channel_override`` property to override the default
   ``channel_name`` from being the name of the app the view exists within.

2.1.1 - 20th February 2026
--------------------------

-  Fixed a bug where the Django permission check was checking the wrong
   class property.

2.1.0 - 12th February 2026
--------------------------

-  Added support to check Django permissions before invoking the handler
   method.
-  This allows methods to be restricted using Django's standard permissions
   system.
-  Added support for a list of permissions where, if the user has any of
   them, they are allowed to invoke the handler method.
-  Added support for a list of permissions where the user must have all of
   them to invoke the handler method.
-  If neither permission list is set, all users are allowed to invoke the
   handler, matching the previous behaviour.
-  Added ``has_any_permission`` for checks where the user must have any of
   the listed permissions.
-  Added ``has_all_permission`` for checks where the user must have all of
   the listed permissions.
-  These methods can be overridden for custom permission handling.

2.0.2 - 30th September 2025
---------------------------

-  Added support for Python 3.14 and Django 6.0a1 into the test suite.

2.0.1 - 30th September 2025
---------------------------

-  ``route_selection_key`` is going to be deprecated and is being replaced
   by ``handler_selection_key``.
-  ``handler_selection_key`` is a more accurate name and has a new default
   value of ``handler`` rather than ``action``.
-  The change was made because ``action`` relates to route selection on AWS
   API Gateway and is more closely tied to additional routes, while
   ``handler`` is more closely related to the handler method being called in
   Django.
-  The code is backward compatible as long as you do not use ``handler``
   within your payload for another purpose.
-  Support for ``route_selection_key`` will be kept in place until March
   2026. After that point, it will be removed.
-  The Django setting used to determine the AWS region has been changed from
   ``AWS_REGION_NAME`` to ``AWS_GATEWAY_REGION_NAME``.
-  If ``AWS_GATEWAY_REGION_NAME`` is not found or is not set, the old
   ``AWS_REGION_NAME`` setting will be used.
-  This change allows Django Storage users to use separate AWS regions.
-  Fixed a bug where using profiles rather than explicit AWS credentials
   resulted in the wrong request building the Boto3 client.

2.0.0 - 30th September 2025 - Yanked
------------------------------------

-  Removed from PyPI due to inclusion of an erroneous debugging print
   statement.

1.4.1 - 8th June 2025
---------------------

-  Introduce two Django CBV mixins to speed up development for projects
   using this library.
-  ``AddWebSocketRouteToContextMixin`` this mixin can vbe added to CBV
   views that need to connect to and send message to the server via
   Websockets. It allows you to specific the ``route_key`` to use to
   idnetify the WebSocket route you created (defaulting to the “default”
   route), as well as adding a class property and context key of
   “channel_name” that can be used within the HTML templates to connect
   to the channel intended to be used by the view.
-  ``AppChannelWebSocketMixin`` this mixin extends the first with the
   intention of being used by CBVs where the both the ``route_key`` and
   ``channel_name`` are the same and *BOTH* are the same names as the
   app. This is useful in the design paradigm where you are going to
   have one WebSocket endpoint per app handling the server-side
   requests. This way you can create the route key to match the Django
   app name and then use this mixin to extend the CBVs that render the
   client facing HTML.

For example if you have the app *blog* with the following CBV defined
within the views.py

::

   class IndexView(AppChannelWebSocketMixin, TemplateView):
       template_name = "blog/index.htm"

Then you create an ``ApiGatewayAdditionalRoute`` entry with a
``route_key`` of **blog** so that the you can then create a Django
template such as the below which can be included on any page on your
project that requires websocket connectivity to define the connection

.. code:: html

   <script src="js/reconnecting-websocket.min.js" crossorigin="anonymous"></script>
   {% with api_gateway_route.api_gateway as websocket %}
   <script
       data-wss-url="wss://{{ websocket.domain_name }}"
       data-ws-channel="{{ channel_name }}"
       data-ws-route-key="{{ api_gateway_route.route_key }}"
   >
   {% endwith %}
   let window.scWebSocketConnected = false;
   let scriptData = document.currentScript.dataset;
   let pageWebSocket = new ReconnectingWebSocket(
       `${scriptData.wssUrl}?channel=${scriptData.wsChannel}`, null, {debug:false, reconnectInterval:3000}
   );

Full examples of how to use this project with re-usable JS for the
client and CBVs for the server will be published soon.

.. _th-june-2025-1:

1.4.0 - 8th June 2025
---------------------

Yanked to bugs - do not use

1.3.0 - 26th May 2025
---------------------

-  Added in support for AWS Profiles
-  Updated the documentation to include examples of how to configure
   settings.py

.. _th-may-2025-1:

1.2.1 - 12th May 2025
---------------------

-  1.2.0 was built using an older version so the package had the wrong
   name, it’s been yanked, so use 1.2.1 instead

1.2.0 - 12th May 2025 - yanked
------------------------------

-  Dropped support for Django 5.0
-  This package should still work with those combinations but they are
   no longer being tested

1.1.3 - 7th May 2025
---------------------

-  Updated pyproject.toml to show Django 5.2 support, also updated the
   pre-commit-config and requirements or testings

1.1.2 - 17th March 2025
-----------------------

-  Removed Python 3.8 support

1.1.1 - 20th November 2024
--------------------------

-  Updated the tox tests to include support for Django 5.2a.1 with
   Python 3.10, 3.11, 3.12, 3.13 and 3.14

1.1.0 - 19th November 2024
--------------------------

-  Fixes possible security issue #17 to remove the direct use of headers
   being passed into the Bad Request Response.
-  Changed the response send by the bad request response
-  Updating requirements

1.0.22 - 21st October 2024
--------------------------

-  Updated github actions to collect and display coverage reports
-  Updated tox to include tests for Python 3.13 with Django 4.2, 5.0 and
   5.1
-  Updated tox to include tests for Python 3.14.0-alpha1 with Django 5.1
-  Updated main.yml to use `UV <https:/yes/github.com/astral-sh/uv>`__
   for faster testing

1.0.21 - 4th August 2024
--------------------------

-  Includes the PR for .github/workflows/main.yml as well as updating to
   show support for Django 5.1

1.0.20 - 15th July 2024
--------------------------

-  Dependency update for security fix

1.0.19 - 11th July 2024
--------------------------

-  Updating the requirements for the pipline to use Django 5.0.7 or
   Django 4.2.14

-  .. rubric:: 1.0.18 - 2nd July 2024
      :name: nd-july-2024

-  Updating the requirements so Python 3.10+ requires urllib3>=2.2.2 due
   to the security issues with 2.0.0 through 2.2.1

1.0.17 - 28th May 2024
--------------------------

-  Bumping required sqlparse version for Django 4.2 and 5.0 to be 0.5.0
   due to security fix for DOS in sqlparse<5.0.0 within the requirements
   files used for testing.

.. _th-may-2024-1:

1.0.16 - 24th May 2024
--------------------------

-  Added in test for Django 5.1a1

.. _th-may-2024-2:

1.0.15 - 7th May 2024
---------------------

-  Upgrade black, blacken-docs and isort within precommit, removed black
   from the requirements as it’s only used by pre-commit

.. _th-may-2024-3:

1.0.14 - 7th May 2024
---------------------

-  Removing support for Django < 4.2.0. This project will probably still
   work with Django 3.2+ but I’m now longer going to support it with
   tests.
-  Bumped requirements as well

1.0.13 - 14th December 2023
---------------------------

-  Adding Django 4.2 into the matrix of tests replacing 4.2a1
-  Adding Django 5 into the tox runner

1.0.12 - 20th September 2023
-----------------------------

-  Updating the README file with additional examples.
-  Adding in additional unit tests to improve coverage from 86% to 96%.
-  Adding Django 4.2 into the matrix of tests replacing 4.2a1
-  Adding Django 5 into the tox runner

1.0.11 - 18th January 2023
--------------------------

-  Adding Django 4.2a1 into the matrix of tests

1.0.10 - 15th December 2022
---------------------------

-  Fixing an issue where ``ApiGatewayAdditionalRoute`` had a unique
   constraint on the ``route_key`` when it should have been a composite
   unique constraint on the ``api_gateway`` and the ``route_key``

.. _th-december-2022-1:

1.0.9 - 12th December 2022
--------------------------

-  Fixing an issue within the dispatch method of the view where the
   route key was missing from the arg. Now continues with the checks.

.. _th-december-2022-2:

1.0.8 - 9th December 2022
--------------------------

-  Corrected the examples of the CSRF and Session values on the README
   file.

.. _th-december-2022-3:

1.0.7 - 9th December 2022
-------------------------

-  Added in tests for Python 3.11
-  Removed use of CodeCov and moved to use GitHUb actions to store and
   report on the coverage.
-  Actions fail if coverage drops below 85%, this threshold will be
   increased in the future as I add in additional tests
-  Updated requirements and removed legacy tox files
-  Updated version of gitHub Actions
-  Added link to the PyPi site from the readme

.. _th-december-2022-4:

1.0.6 - 9th December 2022
--------------------------

-  Updating the listing pages to include whether the additional route
   has been deployed or not
-  Updated the README file

.. _th-december-2022-5:

1.0.0 - 1.0.5 - 8th December 2022
---------------------------------

-  Added support for additional custom routes for each API. This means
   that you could use one API Gateway for an entire project if you
   wished to using the ``ApiGatewayAdditionalRoute`` to route requests
   to different URLs within your project. This is extremely useful if
   you have multiple apps that require websockets. The recommendation is
   to have a central view that handles all connections, disconnections
   and the default route. Then to use specific route for each of your
   apps, views or however you require to separate requests.

0.2.2 - 20th September 2022
----------------------------

-  Added in additional unit tests. Still requires additional tests for
   full coverage

.. _th-september-2022-1:

0.2.1 - 13th September 2022
---------------------------

-  BUG FIX - The ``_create_domain_name`` method of the ``ApiGateway``
   was always setting a hosted zone id even if one was not to be used.
-  Updating the README.md file with the updated IAM policy

.. _th-september-2022-2:

0.2.0 - 12th September 2022
---------------------------

-  Updating the packaging of the project as the management command was
   not being bundled with the rest of the code.

0.1.5 - 4th August 2022
-----------------------

-  Adding in a supplementary list of headers that are also required, by
   default, but that you may need to blank out when testing from a
   non-AWS deployment such as via na ngrok proxy
-  Adding the management command to stale connections

.. _th-august-2022-1:

0.1.4 - 4th August 2022
-----------------------

-  Correcting the name on the license
-  Updating the README setup instructions including the required Django
   settings
-  Adding Exception handling into the Django Admin page so that the
   exceptions are caught and added to Django messages
-  Ensures the trailing / is appended to the target base endpoint.

.. _th-august-2022-2:

0.1.3 - 4th August 2022
-----------------------

-  License is now MIT
-  Now considered as in Beta
-  Supports Django 3.2, 4.0 and 4.1
-  Supports Python 3.8 through 3.10

0.1.2 - 29th June 2022
----------------------

-  Updated the dispatch method of WebSocketView to add in the default
   positive response if the handling method that was called does not
   return a response. This means that unless you are returning a
   negative response the handling methods no longer need to return
   anything.

-  Updated the README with examples of writing individual methods to
   handle different types of requests where the type of request is
   determined by the value of the ``route_selection_key``.

-  Updated the README with examples of how to send a reply to the
   websocket that made the request as well as how to send a Multicast to
   all connections using the same “channel”.

-  .. rubric:: 0.1.1 - 25th June 2022
      :name: th-june-2022-1

-  Added debugging list to the base ``WebSocketView`` to keep track of
   calls if debugging is turned on. The intention is that debug=True can
   be passed into the ``.as_view()`` method in order to debug issues.
   Then the dispatch method can be overloaded to log the error to the
   logger the user wishes to use.

-  Fixed a bug with the custom QuerySet so that if a ``GoneException``
   is raised by boto3 then the websocket session entry is updated to be
   flagged as no longer connected

.. _th-june-2022-2:

0.1.0 - 8th June 2022
---------------------

-  The channel set against the ``WebSocketSession`` is now determine by
   a new method. The method looks at the QueryString first of all and if
   that it empty it then uses the default_channel_name set against the
   ``APIGateway`` record that was found
-  Fixed a bug with \_check_platform_registered_api_gateways to fix the
   NoneType issue
-  Added the missing ``__str__`` method into the class as well as
   removing the import that is no longer used
-  Added the missing ``self.custom_domain_created = True`` into the
   ``create_custom_domain`` method
-  Fixed a bug where formatting had converted the hosted zone id into a
   tuple
-  Fixed a bug around the boto3 client setup as the checks for the
   AWS_ACCESS_KEY were not tight enough so I’ve swapped the order
-  Fixed a bug where method name was typed wrong
-  Fixed a bug where the wrong admin view had the custom actions
-  Added new property to the base View called ``websocket_session``
   which stores the websocket session for the request for all non
   connect or disconnect requests
-  Added ``send_message`` method to the WebSocketSession class in order
   to send a message to the connection
-  Added a new custom queryset class called ``WebSocketSessionQuerySet``
   that implements a method to send a message to every object within the
   current filter whilst ensuring it only sends to connections that are
   active
-  Added the model ``ApiGateway``
-  Updated ``WebSocketView`` to include validation of the
   ``aws_api_gateway_id`` property to allow views to be created that
   only allow specific API Gateway endpoints to call them.
-  Updated ``WebSocketView`` to include validation of the calling API
   Gateway endpoint to check that it’s one of the APIGateway records
   registered with the platform. **Note: Could do with updating to check
   a cache first**
-  ``WebSocketSession`` now stores an FK to ``ApiGateway`` and is
   populated by the WebSocketView within the connection method
-  The API Gateway ID within the header is now always checked against
   the database to help block unexpected sources.
-  Added two custom Django Admin functions ``create_api_gateway`` and
   ``create_custom_domain`` that can be used to create the actual AWS
   API Gateway endpoint and custom domain.
-  Added two management commands ``createApiGateway`` and
   ``createCustomDomain`` both of which take one parameter which is the
   PK of the ApiGateway record you wish to run. These management
   commands run the same methods the admin functions added above. They
   have been created to allow this package to be used without Django
   Admin but to still be able to automatically set-up API Gateway
-  Created the initial logic to create the API Gateway and the Custom
   Domain as methods of the ApiGateway model. The intended use is to
   call ``obj.create_create_gateway()`` first then to call
   ``obj.create_custom_domain()`` once the SSL certificate is ready.
   These methods will update the record with the details required to
   update Route53

0.0.1 - 17th Jan 2022
---------------------

-  Initial build with the base view and base model.
-  Dropped support for Django < 3.1 due to use of PositiveBigInt and
   also drop support of Python < 3.8
