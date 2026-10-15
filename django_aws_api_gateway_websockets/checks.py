"""System checks for the gateway secret, channel access and the ``WEBSOCKETS`` setting.

Run ``python manage.py check --deploy`` to see the deployment warnings.
"""

from django.conf import settings
from django.core import checks
from django.urls import URLPattern, URLResolver, get_resolver

from django_aws_api_gateway_websockets.conf import (
    BOOLEAN_DEFAULTS,
    DEFAULTS,
    KNOWN_KEYS,
)
from django_aws_api_gateway_websockets.models import GATEWAY_SECRET_PATTERN


def _configured_secrets() -> list:
    websockets = getattr(settings, "WEBSOCKETS", None) or {}
    configured = websockets.get("gateway_secret")
    if configured in (None, ""):
        return []
    if isinstance(configured, (list, tuple)):
        return [secret for secret in configured if secret not in (None, "")]
    return [configured]


@checks.register(checks.Tags.security)
def check_gateway_secret_format(app_configs, **kwargs):
    """Error if a configured gateway secret could not be used safely.

    The message never includes the secret.
    """
    for secret in _configured_secrets():
        if not isinstance(secret, str) or not GATEWAY_SECRET_PATTERN.fullmatch(secret):
            return [
                checks.Error(
                    'WEBSOCKETS["gateway_secret"] is not a valid secret.',
                    hint=(
                        "Use a string, or a list of strings, of at least 32 characters "
                        "from A-Z a-z 0-9 . _ ~ + / = -, with no newline or other "
                        "whitespace. Strip the newline from a secret read from a file."
                    ),
                    id="django_aws_api_gateway_websockets.E001",
                )
            ]
    return []


@checks.register(checks.Tags.security, deploy=True)
def check_gateway_secret_is_set(app_configs, **kwargs):
    """Warn when no gateway secret is set, because the gateway is then not authenticated."""
    if _configured_secrets():
        return []
    return [
        checks.Warning(
            'WEBSOCKETS["gateway_secret"] is not set.',
            hint=(
                "Any client that sends the headers API Gateway normally adds, and knows a "
                "registered API ID, can send requests to the WebSocket view. Set a gateway "
                "secret and update the integrations. See the Gateway secret section of the "
                "security documentation."
            ),
            id="django_aws_api_gateway_websockets.W001",
        )
    ]


def _url_patterns() -> list:
    """The project's URL patterns, nested includes and all"""
    found = []
    pending = list(get_resolver().url_patterns)
    while pending:
        pattern = pending.pop(0)
        if isinstance(pattern, URLResolver):
            pending.extend(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            found.append(pattern)
    return found


def _routed_view_classes() -> list:
    """The ``WebSocketView`` subclasses that the project routes, each once"""
    from django_aws_api_gateway_websockets.views import WebSocketView

    views = []
    for pattern in _url_patterns():
        view_class = getattr(pattern.callback, "view_class", None)
        if (
            isinstance(view_class, type)
            and issubclass(view_class, WebSocketView)
            and view_class not in views
        ):
            views.append(view_class)
    return views


def _routed_views_allowing_unlisted_channels() -> list:
    """Routed ``WebSocketView`` subclasses that let anyone join an unlisted channel"""
    return [view for view in _routed_view_classes() if view.ALLOW_UNLISTED_CHANNELS]


@checks.register(checks.Tags.security, deploy=True)
def check_handlers_are_listed(app_configs, **kwargs):
    """Warn for each routed view that builds its handler list from its own public methods.

    Every method such a view defines can be called by name from any connected client, so a
    helper added later becomes reachable without anyone deciding that it should be.
    """
    messages = []
    for view in _routed_view_classes():
        exposed = sorted(set(view._automatic_handlers()) - view.BASE_HANDLERS)
        if view.ALLOWED_HANDLERS or not exposed:
            continue
        messages.append(
            checks.Warning(
                f"{view.__module__}.{view.__qualname__} has no ALLOWED_HANDLERS, so clients "
                f"can call {', '.join(exposed)}.",
                hint=(
                    "Set ALLOWED_HANDLERS to the names clients may call, such as "
                    '{"default", "chat"}. Without it, every public method you add to the '
                    "view becomes callable from the WebSocket."
                ),
                id="django_aws_api_gateway_websockets.W005",
            )
        )
    return messages


@checks.register(checks.Tags.security, deploy=True)
def check_unlisted_channels_are_refused(app_configs, **kwargs):
    """Warn for each routed view that lets anyone join a channel that has no rule."""
    return [
        checks.Warning(
            f"{view.__module__}.{view.__qualname__} allows channels that have no "
            "ChannelPermission row.",
            hint=(
                "Anyone who can connect can join a channel with no rule, and a "
                "mistyped or forgotten channel name is open. Set "
                "ALLOW_UNLISTED_CHANNELS = False on the view, and add an Allow all "
                "row for each public channel. The default is planned to change in a "
                "future major version. See the Channel permissions documentation."
            ),
            id="django_aws_api_gateway_websockets.W004",
        )
        for view in _routed_views_allowing_unlisted_channels()
    ]


@checks.register(checks.Tags.compatibility)
def check_websockets_setting(app_configs, **kwargs):
    """Report a ``WEBSOCKETS`` dictionary that is the wrong type, has a bad value, or has a typo.

    Messages name the keys and never include values.
    """
    configured = getattr(settings, "WEBSOCKETS", None)
    if configured is None:
        return []
    if not isinstance(configured, dict):
        return [
            checks.Error(
                "WEBSOCKETS must be a dictionary.",
                id="django_aws_api_gateway_websockets.E002",
            )
        ]

    messages = []
    for name in DEFAULTS:
        if name not in configured:
            continue
        value = configured[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            messages.append(
                checks.Error(
                    f'WEBSOCKETS["{name}"] must be a whole number of 1 or more.',
                    hint=f"The default of {DEFAULTS[name]} is used until it is fixed.",
                    id="django_aws_api_gateway_websockets.E002",
                )
            )
    for name in BOOLEAN_DEFAULTS:
        if name in configured and not isinstance(configured[name], bool):
            messages.append(
                checks.Error(
                    f'WEBSOCKETS["{name}"] must be True or False.',
                    hint=(
                        f"The default of {BOOLEAN_DEFAULTS[name]} is used until it is fixed."
                    ),
                    id="django_aws_api_gateway_websockets.E002",
                )
            )
    hosts = configured.get("allowed_integration_hosts")
    if hosts is not None and not (
        (isinstance(hosts, str) and hosts.strip())
        or (
            isinstance(hosts, (list, tuple))
            and all(isinstance(host, str) and host.strip() for host in hosts)
        )
    ):
        messages.append(
            checks.Error(
                'WEBSOCKETS["allowed_integration_hosts"] must be a host name or a list '
                "of host names.",
                hint=(
                    "Any host is allowed until it is fixed. Use names such as "
                    '"www.example.com" or "*.example.com".'
                ),
                id="django_aws_api_gateway_websockets.E002",
            )
        )
    for name in sorted(set(configured) - KNOWN_KEYS, key=str):
        messages.append(
            checks.Warning(
                f'WEBSOCKETS has an unknown key "{name}", which is ignored.',
                hint="Known keys: " + ", ".join(sorted(KNOWN_KEYS)),
                id="django_aws_api_gateway_websockets.W002",
            )
        )
    return messages


@checks.register(checks.Tags.compatibility, deploy=True)
def check_aws_region_is_set(app_configs, **kwargs):
    """Warn when no AWS region is set, which otherwise fails only when the first message is sent."""
    if getattr(settings, "AWS_GATEWAY_REGION_NAME", "") or getattr(
        settings, "AWS_REGION_NAME", ""
    ):
        return []
    return [
        checks.Warning(
            "No AWS region is set.",
            hint=(
                "Set AWS_GATEWAY_REGION_NAME (or AWS_REGION_NAME). Without it, creating "
                "gateways and sending messages fails."
            ),
            id="django_aws_api_gateway_websockets.W003",
        )
    ]
