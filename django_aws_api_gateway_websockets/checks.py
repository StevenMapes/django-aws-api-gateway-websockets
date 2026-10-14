"""System checks for the optional gateway secret.

Run ``python manage.py check --deploy`` to see the warning.
"""

from django.conf import settings
from django.core import checks

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
