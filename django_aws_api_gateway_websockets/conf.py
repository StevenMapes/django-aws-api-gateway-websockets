"""The optional ``WEBSOCKETS`` settings dictionary, read in one place.

Every component reads its values through :func:`get_setting`, so a setting has one
default and one meaning wherever it is used.
"""

from django.conf import settings

DEFAULTS = {
    # The number of tokens a user can request per minute
    "token_rate_limit_per_minute": 20,
    # The time, in seconds, that a token is valid for. Reported to the client and enforced
    "token_expiry_seconds": 60,
    # The number of connection attempts allowed within the rate limit window
    "rate_limit_max_attempts": 20,
    # The rate limit window for connection attempts
    "rate_limit_window_minutes": 1,
}

BOOLEAN_DEFAULTS = {
    # Whether saving or deleting a deployed gateway or route also changes it in AWS. Turn it
    # off to change only the local records, as before syncing with AWS existed. A new route
    # is still created in AWS when it is saved, either way.
    "push_changes_to_aws": True,
}

# Keys that are read from the dictionary but have no default
OPTIONAL_KEYS = frozenset({"gateway_secret", "allowed_integration_hosts"})

KNOWN_KEYS = frozenset(DEFAULTS) | frozenset(BOOLEAN_DEFAULTS) | OPTIONAL_KEYS


def get_websockets_config() -> dict:
    """Return the ``WEBSOCKETS`` dictionary, or an empty one if it is unset or not a dictionary."""
    configured = getattr(settings, "WEBSOCKETS", None)
    return configured if isinstance(configured, dict) else {}


def get_setting(name: str) -> int:
    """Return a numeric setting, or its default.

    A value that is not a positive integer is ignored in favour of the default. The system
    check ``django_aws_api_gateway_websockets.E002`` reports it at start-up.

    :raises KeyError: If ``name`` is not a setting with a default.
    """
    default = DEFAULTS[name]
    value = get_websockets_config().get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


def get_boolean_setting(name: str) -> bool:
    """Return a ``True`` or ``False`` setting, or its default.

    A value that is not a boolean is ignored in favour of the default. The system check
    ``django_aws_api_gateway_websockets.E002`` reports it at start-up.

    :raises KeyError: If ``name`` is not a boolean setting.
    """
    default = BOOLEAN_DEFAULTS[name]
    value = get_websockets_config().get(name, default)
    return value if isinstance(value, bool) else default


def get_allowed_integration_hosts() -> list[str]:
    """Return the hosts an API Gateway integration may point at, in lower case.

    ``WEBSOCKETS["allowed_integration_hosts"]`` is a host name or a list of them. An entry
    that starts with ``*.`` matches the sub-domains of the rest, and not the domain itself.
    An empty list, which is the default, means any host. Entries that are not text are ignored.
    The system check ``django_aws_api_gateway_websockets.E002`` reports them at start-up.
    """
    configured = get_websockets_config().get("allowed_integration_hosts")
    if isinstance(configured, str):
        configured = [configured]
    if not isinstance(configured, (list, tuple)):
        return []
    hosts = []
    for host in configured:
        if isinstance(host, str) and host.strip():
            hosts.append(host.strip().lower())
    return hosts
