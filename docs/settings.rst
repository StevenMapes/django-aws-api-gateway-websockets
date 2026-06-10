Settings
========

This page documents the Django settings and view-level configuration options
commonly used with Django-AWS-API-Gateway-WebSockets.

The package uses a combination of:

* project-level Django settings;
* AWS credential settings;
* normal Django security settings;
* class attributes on ``WebSocketView`` subclasses;
* model fields stored in the database.

Project installation
--------------------

Add the package to ``INSTALLED_APPS``.

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "django_aws_api_gateway_websockets",
   ]

Then run migrations.

.. code-block:: console

   python manage.py migrate

AWS credential settings
-----------------------

The package uses Boto3 to interact with AWS.

It supports several credential approaches.

AWS_GATEWAY_REGION_NAME
~~~~~~~~~~~~~~~~~~~~~~~

Sets the AWS region used for API Gateway operations.

Example:

.. code-block:: python

   AWS_GATEWAY_REGION_NAME = "eu-west-1"

This is the recommended region setting for this package.

If your application runs on AWS with an attached IAM role, this may be the only
AWS setting you need.

AWS_REGION_NAME
~~~~~~~~~~~~~~~

Fallback AWS region setting.

If ``AWS_GATEWAY_REGION_NAME`` is not set, the package can fall back to
``AWS_REGION_NAME``.

Example:

.. code-block:: python

   AWS_REGION_NAME = "eu-west-1"

Prefer ``AWS_GATEWAY_REGION_NAME`` for new projects because it is more specific
to this package.

AWS_IAM_PROFILE
~~~~~~~~~~~~~~~

Use a named AWS profile.

This is useful for local development where credentials are stored in your AWS
configuration files.

Example:

.. code-block:: python

   AWS_IAM_PROFILE = "default"

When this setting is used, Boto3 creates a session with the named profile.

If the profile includes a region, you may not need to set
``AWS_GATEWAY_REGION_NAME`` separately.

AWS_ACCESS_KEY_ID
~~~~~~~~~~~~~~~~~

Explicit AWS access key.

Example:

.. code-block:: python

   AWS_ACCESS_KEY_ID = "your-access-key"

Do not commit real access keys to source control.

AWS_SECRET_ACCESS_KEY
~~~~~~~~~~~~~~~~~~~~~

Explicit AWS secret access key.

Example:

.. code-block:: python

   AWS_SECRET_ACCESS_KEY = "your-secret-key"

Do not commit real secret keys to source control.

Explicit credential example
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   AWS_ACCESS_KEY_ID = "your-access-key"
   AWS_SECRET_ACCESS_KEY = "your-secret-key"
   AWS_GATEWAY_REGION_NAME = "eu-west-1"

Credential priority
~~~~~~~~~~~~~~~~~~~

The package supports the following credential styles:

#. named profile using ``AWS_IAM_PROFILE``;
#. explicit access key and secret key;
#. environment or instance role credentials with a configured region.

For production deployments, prefer IAM roles where possible.

See :doc:`aws_iam_setup`.

Required region
~~~~~~~~~~~~~~~

A region is required when creating Boto3 clients without a named profile that
already provides one.

If no region can be found, the package raises an error.

Django security settings
------------------------

ALLOWED_HOSTS
~~~~~~~~~~~~~

Configure Django's allowed hosts.

Example:

.. code-block:: python

   ALLOWED_HOSTS = [
       "www.example.com",
       "example.com",
   ]

If testing through a tunnel, include the tunnel host.

Example:

.. code-block:: python

   ALLOWED_HOSTS = [
       "localhost",
       "127.0.0.1",
       "example-tunnel.ngrok-free.app",
   ]

CSRF_TRUSTED_ORIGINS
~~~~~~~~~~~~~~~~~~~~

Configure trusted origins for CSRF-protected token requests.

Example:

.. code-block:: python

   CSRF_TRUSTED_ORIGINS = [
       "https://www.example.com",
   ]

If your site and WebSocket-related token endpoint use subdomains, include the
required origins.

Example:

.. code-block:: python

   CSRF_TRUSTED_ORIGINS = [
       "https://www.example.com",
       "https://ws.example.com",
   ]

SESSION_COOKIE_DOMAIN
~~~~~~~~~~~~~~~~~~~~~

If your Django site and WebSocket endpoint use related subdomains, configure the
session cookie domain carefully.

Example:

.. code-block:: python

   SESSION_COOKIE_DOMAIN = ".example.com"

This allows the session cookie to be shared across subdomains such as:

.. code-block:: text

   www.example.com
   ws.example.com

Only scope cookies as broadly as required.

CSRF_COOKIE_DOMAIN
~~~~~~~~~~~~~~~~~~

If CSRF tokens need to be available across related subdomains, configure the
CSRF cookie domain.

Example:

.. code-block:: python

   CSRF_COOKIE_DOMAIN = ".example.com"

SESSION_COOKIE_SAMESITE
~~~~~~~~~~~~~~~~~~~~~~~

Controls SameSite behaviour for the session cookie.

Example:

.. code-block:: python

   SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SAMESITE
~~~~~~~~~~~~~~~~~~~~

Controls SameSite behaviour for the CSRF cookie.

Example:

.. code-block:: python

   CSRF_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE
~~~~~~~~~~~~~~~~~~~~~

For production HTTPS deployments, enable secure session cookies.

.. code-block:: python

   SESSION_COOKIE_SECURE = True

CSRF_COOKIE_SECURE
~~~~~~~~~~~~~~~~~~

For production HTTPS deployments, enable secure CSRF cookies.

.. code-block:: python

   CSRF_COOKIE_SECURE = True

SESSION_COOKIE_NAME
~~~~~~~~~~~~~~~~~~~

If changing cookie domain behaviour during an upgrade or deployment, you may
choose to rename the session cookie so old incompatible cookies are ignored.

Example:

.. code-block:: python

   SESSION_COOKIE_NAME = "mysessionid"

After changing session cookie settings, consider clearing old sessions.

.. code-block:: console

   python manage.py clearsessions

Subdomain example
-----------------

If your main site is:

.. code-block:: text

   https://www.example.com

and your WebSocket endpoint is:

.. code-block:: text

   wss://ws.example.com

you may need settings similar to:

.. code-block:: python

   ALLOWED_HOSTS = [
       "www.example.com",
   ]

   CSRF_TRUSTED_ORIGINS = [
       "https://www.example.com",
       "https://ws.example.com",
   ]

   CSRF_COOKIE_DOMAIN = ".example.com"
   SESSION_COOKIE_DOMAIN = ".example.com"

   CSRF_COOKIE_SAMESITE = "Lax"
   SESSION_COOKIE_SAMESITE = "Lax"

   CSRF_COOKIE_SECURE = True
   SESSION_COOKIE_SECURE = True

If your WebSocket token endpoint is served from your main Django site rather
than the WebSocket domain, adjust origins and cookie settings to match your
actual deployment.

WEBSOCKETS
----------

A dictionary that controls the WebSocket token settings as well as the rate limiting without needing to subclass the
WebSocketView and WebSocketToken classes. All keys shown below are optional, all values shown below are the defaults

.. code-block:: python
    WEBSOCKETS = {
        "token_rate_limit_per_minute": 20,  # The number of tokens a user can request per minute
        "token_expiry_seconds": 60,  # The time, in seconds, that the token is valid for
        "rate_limit_max_attempts": 20,  # The number of connection attempts a user can make within the rate limit window
        "rate_limit_window_minutes": 1,  # The rate limit window for the connection attempts
    }


WebSocketView settings
----------------------

Many runtime options are configured as class attributes on your
``WebSocketView`` subclass.

SEND_EXCEPTION_MAIL
~~~~~~~~~~~~~~~~~~~

Controls whether the project sends an email via ``mail_admins``  if an exception is raised during the dispatch method
calling the handler function

Default: True

.. code-block:: python

   SEND_EXCEPTION_MAIL = False


USE_WS_TOKEN
~~~~~~~~~~~~

Controls whether WebSocket token validation is required during connection.

Default:

.. code-block:: python

   USE_WS_TOKEN = True

Recommended for authenticated production connections.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       USE_WS_TOKEN = True

       def default(self, request, *args, **kwargs):
           return None

For public or local-only test endpoints, you can disable token validation.

.. code-block:: python

   class PublicWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           return None

See :doc:`websocket_tokens`.

RATE_LIMIT_ENABLED
~~~~~~~~~~~~~~~~~~

Controls whether connection attempt rate limiting is enabled.

Default:

.. code-block:: python

   RATE_LIMIT_ENABLED = True

RATE_LIMIT_MAX_ATTEMPTS
~~~~~~~~~~~~~~~~~~~~~~~

Maximum connection attempts allowed within the configured window.

Default:

.. code-block:: python

   RATE_LIMIT_MAX_ATTEMPTS = 20

RATE_LIMIT_WINDOW_MINUTES
~~~~~~~~~~~~~~~~~~~~~~~~~

Time window for connection attempt rate limiting.

Default:

.. code-block:: python

   RATE_LIMIT_WINDOW_MINUTES = 5

Example:

.. code-block:: python

   class NotificationsWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 40
       RATE_LIMIT_WINDOW_MINUTES = 5

       def default(self, request, *args, **kwargs):
           return None

See :doc:`rate_limiting`.

MAX_BODY_SIZE
~~~~~~~~~~~~~

Maximum incoming request body size in bytes.

Default:

.. code-block:: python

   MAX_BODY_SIZE = 1024 * 128

This is 128KB.

MAX_CHANNEL_NAME_LENGTH
~~~~~~~~~~~~~~~~~~~~~~~

Maximum channel name length.

Example:

.. code-block:: python

   MAX_CHANNEL_NAME_LENGTH = 191

CHANNEL_NAME_PATTERN
~~~~~~~~~~~~~~~~~~~~

Regular expression used to validate channel names.

The default allows letters, numbers, underscores, and hyphens.

Use simple, safe channel names such as:

.. code-block:: text

   general
   support
   tenant_123
   notifications_user_456

Avoid storing sensitive data directly in channel names.

ALLOWED_HANDLERS
~~~~~~~~~~~~~~~~

Explicit set of handler methods the client is allowed to request.

Example:

.. code-block:: python

   class ChatWebSocketView(WebSocketView):
       ALLOWED_HANDLERS = {
           "default",
           "send_message",
           "fetch_history",
       }

       def send_message(self, request, *args, **kwargs):
           return None

       def fetch_history(self, request, *args, **kwargs):
           return None

       def default(self, request, *args, **kwargs):
           return None

Use this to prevent arbitrary method invocation.

ADDITIONAL_ALLOWED_HANDLERS
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Allows extra handler names to be added to the automatically detected handlers.

This can be useful when subclassing views across multiple layers.

Example:

.. code-block:: python

   class BaseChatWebSocketView(WebSocketView):
       ADDITIONAL_ALLOWED_HANDLERS = [
           "send_message",
           "fetch_history",
       ]

route_selection_key
~~~~~~~~~~~~~~~~~~~

Legacy key used to select handlers from the request body.

Default:

.. code-block:: python

   route_selection_key = "action"

Many examples use ``action`` because it is also commonly used by API Gateway's
route selection expression.

handler_selection_key
~~~~~~~~~~~~~~~~~~~~~

Preferred key for selecting Django-side handlers from the request body.

Default:

.. code-block:: python

   handler_selection_key = "handler"

For larger projects, you may use:

* ``action`` for API Gateway route selection;
* ``handler`` for Django handler selection.

Keep the frontend payload, API Gateway route selection expression, and Django
view configuration aligned.

permissions_required
~~~~~~~~~~~~~~~~~~~~

List of Django permissions where the user must have at least one permission.

Example:

.. code-block:: python

   class ChatWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
       ]

       def default(self, request, *args, **kwargs):
           return None

all_permissions_required
~~~~~~~~~~~~~~~~~~~~~~~~

List of Django permissions where the user must have all permissions.

Example:

.. code-block:: python

   class ModerationWebSocketView(WebSocketView):
       all_permissions_required = [
           "chat.can_use_chat",
           "chat.can_moderate_chat",
       ]

       def default(self, request, *args, **kwargs):
           return None

See :doc:`permissions`.

aws_api_gateway_id
~~~~~~~~~~~~~~~~~~

Optional API Gateway ID restriction.

If set, the view only accepts requests from that specific API Gateway ID.

Example:

.. code-block:: python

   class ProductionWebSocketView(WebSocketView):
       aws_api_gateway_id = "abc123"

       def default(self, request, *args, **kwargs):
           return None

required_headers
~~~~~~~~~~~~~~~~

Headers expected on API Gateway requests.

Most users should not change this.

If testing locally through a tunnel or proxy, some headers may be missing. Only
relax header checks in development and only when you understand the impact.

additional_required_headers
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Additional headers expected on API Gateway requests.

These may vary in local development depending on proxy or tunnel behaviour.

required_connection_headers
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Headers expected during WebSocket connection.

These are checked during the connect route.

expected_useragent_prefix
~~~~~~~~~~~~~~~~~~~~~~~~~

Expected API Gateway user-agent prefix.

Most users should not change this.

Mixin settings
--------------

AddWebSocketRouteToContextMixin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The template mixin uses these attributes:

``websocket_route_key``
   Route key used to look up an additional route.

``channel_name``
   Channel name added to the template context.

Example:

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AddWebSocketRouteToContextMixin


   class DashboardView(AddWebSocketRouteToContextMixin, TemplateView):
       template_name = "dashboard.html"
       websocket_route_key = "dashboard"
       channel_name = "dashboard"

AppChannelWebSocketMixin
~~~~~~~~~~~~~~~~~~~~~~~~

This mixin derives the route key and channel name from the Django app name.

It also supports:

``app_channel_override``
   Override the automatically selected channel name.

Example:

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AppChannelWebSocketMixin


   class DashboardView(AppChannelWebSocketMixin, TemplateView):
       template_name = "dashboard.html"
       app_channel_override = "custom_dashboard_channel"

See :doc:`templates_and_mixins`.

ApiGateway model configuration
------------------------------

Some important configuration is stored in the ``ApiGateway`` model rather than
Django settings.

Important fields include:

``api_name``
   Human-friendly API Gateway name.

``default_channel_name``
   Default channel name when the client does not specify one.

``domain_name``
   Custom WebSocket domain, such as ``ws.example.com``.

``target_base_endpoint``
   Django callback URL excluding the final route slug.

``certificate_arn``
   AWS Certificate Manager certificate ARN.

``hosted_zone_id``
   Route 53 hosted zone ID.

``route_selection_expression``
   API Gateway route selection expression.

``stage_name``
   API Gateway stage name.

See :doc:`models` and :doc:`api_gateway_setup`.

Recommended production settings
-------------------------------

A typical production setup might include:

.. code-block:: python

   DEBUG = False

   ALLOWED_HOSTS = [
       "www.example.com",
   ]

   CSRF_TRUSTED_ORIGINS = [
       "https://www.example.com",
       "https://ws.example.com",
   ]

   CSRF_COOKIE_DOMAIN = ".example.com"
   SESSION_COOKIE_DOMAIN = ".example.com"

   CSRF_COOKIE_SAMESITE = "Lax"
   SESSION_COOKIE_SAMESITE = "Lax"

   CSRF_COOKIE_SECURE = True
   SESSION_COOKIE_SECURE = True

   AWS_GATEWAY_REGION_NAME = "eu-west-1"

And a WebSocket view might include:

.. code-block:: python

   class ProductionWebSocketView(WebSocketView):
       USE_WS_TOKEN = True

       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 20
       RATE_LIMIT_WINDOW_MINUTES = 5

       ALLOWED_HANDLERS = {
           "default",
           "send_message",
           "fetch_history",
       }

       permissions_required = [
           "chat.can_use_chat",
       ]

       def default(self, request, *args, **kwargs):
           return None

Recommended local settings
--------------------------

For local development with a tunnel:

.. code-block:: python

   DEBUG = True

   ALLOWED_HOSTS = [
       "localhost",
       "127.0.0.1",
       "example-tunnel.ngrok-free.app",
   ]

   CSRF_TRUSTED_ORIGINS = [
       "https://example-tunnel.ngrok-free.app",
   ]

   AWS_IAM_PROFILE = "default"
   AWS_GATEWAY_REGION_NAME = "eu-west-1"

See :doc:`local_development`.

Security notes
--------------

Do not commit secrets
~~~~~~~~~~~~~~~~~~~~~

Do not commit:

* AWS access keys;
* AWS secret keys;
* production domain secrets;
* PyPI tokens;
* unrelated service credentials.

Use environment variables, IAM roles, or a secrets manager.

Prefer IAM roles
~~~~~~~~~~~~~~~~

For production, prefer IAM roles or task roles over static access keys.

Keep tokens enabled
~~~~~~~~~~~~~~~~~~~

For authenticated production WebSocket endpoints, keep ``USE_WS_TOKEN`` enabled.

Keep rate limiting enabled
~~~~~~~~~~~~~~~~~~~~~~~~~~

For public or authenticated production endpoints, keep rate limiting enabled.

Validate channels
~~~~~~~~~~~~~~~~~

Do not rely on channel names as authorization.

Check permissions server-side before allowing access to sensitive channels.

Related pages
-------------

See also:

* :doc:`configuration`;
* :doc:`aws_iam_setup`;
* :doc:`api_gateway_setup`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`permissions`;
* :doc:`templates_and_mixins`;
* :doc:`deployment`;
* :doc:`local_development`;
* :doc:`troubleshooting`.
