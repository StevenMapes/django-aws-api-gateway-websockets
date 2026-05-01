# Django AWS API Gateway WebSockets

[![CI Build Status](https://img.shields.io/github/actions/workflow/status/StevenMapes/django-aws-api-gateway-websockets/main.yml?branch=main&style=for-the-badge)](https://github.com/StevenMapes/django-aws-api-gateway-websockets/actions)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/StevenMapes/django-aws-api-gateway-websockets/badges/coverage.json&style=for-the-badge)](https://github.com/StevenMapes/django-aws-api-gateway-websockets/actions?workflow=CI)
[![PyPI](https://img.shields.io/pypi/v/django-aws-api-gateway-websockets.svg?style=for-the-badge)](https://pypi.org/project/django-aws-api-gateway-websockets/)
[![Read the Docs](https://img.shields.io/readthedocs/django-aws-api-gateway-websockets?style=for-the-badge)](https://django-aws-api-gateway-websockets.readthedocs.io/)
[![Python](https://img.shields.io/pypi/pyversions/django-aws-api-gateway-websockets.svg?style=for-the-badge)](https://pypi.org/project/django-aws-api-gateway-websockets/)
[![Django](https://img.shields.io/pypi/djversions/django-aws-api-gateway-websockets.svg?style=for-the-badge)](https://pypi.org/project/django-aws-api-gateway-websockets/)
[![License](https://img.shields.io/github/license/StevenMapes/django-aws-api-gateway-websockets?style=for-the-badge)](LICENSE)

Django AWS API Gateway WebSockets lets Django projects use AWS API Gateway
WebSocket APIs without running a dedicated WebSocket server.

AWS API Gateway manages the WebSocket connection. Django receives API Gateway
events as normal HTTP requests and can send messages back to connected clients
through the AWS API Gateway Management API.

This project is designed for Django applications that want WebSocket-style
features while keeping a traditional Django request/response deployment model.

## Documentation

Full documentation is available on Read the Docs:

<https://django-aws-api-gateway-websockets.readthedocs.io/>

Useful starting points:

- [Quickstart](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/quickstart/)
- [Concepts](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/concepts/)
- [API Gateway setup](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/api_gateway_setup/)
- [Client integration](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/client_integration/)
- [Security](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/security/)
- [WebSocket tokens](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/websocket_tokens/)
- [Deployment](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/deployment/)
- [Troubleshooting](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/troubleshooting/)

## Features

- Handle AWS API Gateway WebSocket events with Django class-based views.
- Track WebSocket connections in the Django database.
- Associate connections with Django users where available.
- Group connections using channels.
- Send messages to:
  - one connection;
  - all connections for a user;
  - all connections in a channel;
  - all connected clients.
- Create and manage API Gateway resources from Django Admin or management commands.
- Add custom API Gateway routes for different Django views.
- Use WebSocket tokens for authenticated connection protection.
- Rate limit WebSocket connection attempts.
- Restrict handlers using Django permissions.
- Use mixins to add WebSocket connection details to template context.

## When to use this package

Use this package if you want:

- AWS API Gateway to manage WebSocket connections;
- Django to receive WebSocket events as HTTP requests;
- to avoid running a dedicated ASGI WebSocket server;
- to send messages from Django to connected browser clients;
- to group connections into channels for multicast messaging;
- to integrate WebSocket behaviour with existing Django models, views, admin,
  permissions, and management commands.

This package is **not** a replacement for
[Django Channels](https://github.com/django/channels). Django Channels is a
better fit if you want Django itself to run an ASGI WebSocket server.

## Requirements

- Python 3.10+
- Django 4.2+
- AWS account with API Gateway permissions
- Boto3-compatible AWS credentials or IAM role

See the
[installation guide](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/installation/)
and
[AWS IAM setup guide](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/aws_iam_setup/)
for details.

## Installation

Install from PyPI:

```bash
pip install django-aws-api-gateway-websockets
```

Add the app to `INSTALLED_APPS`:

```
INSTALLED_APPS += ["django-aws-api-gateway-websockets"]
```

Run migrations:

```bash
python manage.py migrate
```

See the full [quickstart](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/quickstart/)
for a working example.

## Minimal example

Add a Django URL route with a `route` slug:

```python
from django.urls import path

from .views import ExampleWebSocketView

urlpatterns = [
    path(
        "ws/<slug:route>",
        ExampleWebSocketView.as_view(),
        name="example_websocket",
    ),
]
```

Create a WebSocket view:

```python
from django.http import JsonResponse
from django_aws_api_gateway_websockets.views import WebSocketView


class ExampleWebSocketView(WebSocketView):
    def default(self, request, *args, **kwargs):
        self.websocket_session.send_message({})
        return JsonResponse({"ok": True})
```

Create a WebSocket view:

```python
from django.http import JsonResponse

from django_aws_api_gateway_websockets.views import WebSocketView


class ExampleWebSocketView(WebSocketView):
    def default(self, request, *args, **kwargs):
        self.websocket_session.send_message(
            {
                "type": "reply",
                "message": "Hello from Django",
            }
        )

        return JsonResponse({"ok": True})
```

Connect from the browser:

```javascript
const socket = new WebSocket("wss://ws.example.com?channel=example");

socket.onmessage = function (event) {
    const message = JSON.parse(event.data);
    console.log("Received:", message);
};

socket.onopen = function () {
    socket.send(JSON.stringify({
        action: "default",
        message: "Hello from the browser"
    }));
};
```

For production usage, read the documentation on [WebSocket tokens](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/websocket_tokens/) and [security](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/security/).
## AWS setup
The package can create and configure API Gateway WebSocket resources using Django Admin actions or management commands.
Typical setup steps:
1. Configure AWS credentials or an IAM role.
2. Create an record. `ApiGateway`
3. Create the AWS API Gateway.
4. Optionally create a custom domain.
5. Configure DNS.
6. Connect from your frontend client.

See the full [API Gateway setup guide](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/api_gateway_setup/).
## Management commands
The package includes management commands for API Gateway setup and cleanup.

```bash
python manage.py createApiGateway --pk=<api_gateway_pk>
python manage.py createCustomDomain --pk=<api_gateway_pk>
python manage.py clearWebSocketSessions
python manage.py cleanupWebSocketTokens
```

See the [management commands documentation](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/management_commands/) for details.

## Security
Version 3.0.0 introduced significant security improvements, including:
- WebSocket token protection;
- single-use session-bound connection tokens;
- connection attempt rate limiting;
- handler whitelisting;
- Django permission checks;
- stricter input validation;
- channel name validation;
- message size validation;
- safer debug output;
- audit logging for admin actions.

For authenticated production WebSocket endpoints, read:
- [Security](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/security/)
- [WebSocket tokens](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/websocket_tokens/)
- [Permissions](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/permissions/)
- [Rate limiting](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/rate_limiting/)

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development
Clone the repository:

```bash
git clone https://github.com/StevenMapes/django-aws-api-gateway-websockets.git
cd django-aws-api-gateway-websockets
```

Install development requirements into your virtual environment.
Run tests:

```bash
pip install pytest-django
coverage erase
python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings
coverage combine
coverage report
```

Build the documentation locally:

```bash
cd docs
pip install -r requirements.txt
make html
```

See the [contributing guide](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/contributing/) for more information.

## Changelog
See the [changelog](https://django-aws-api-gateway-websockets.readthedocs.io/en/latest/changelog/) for release history.

## License
This project is licensed under the MIT License.
See [LICENSE](LICENSE).
