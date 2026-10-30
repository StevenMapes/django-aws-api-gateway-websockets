import json
import logging
import os
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from functools import partial
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.signals import user_logged_out
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import RegexValidator
from django.db import models, router, transaction
from django.db.models import Count, Prefetch, Q, prefetch_related_objects
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _

from django_aws_api_gateway_websockets import sync
from django_aws_api_gateway_websockets.conf import (
    get_allowed_integration_hosts,
    get_boolean_setting,
    get_websockets_config,
)
from django_aws_api_gateway_websockets.sync import ApiGatewaySyncError

MAX_MESSAGE_SIZE = 1024 * 128  # 128KB (AWS limit is 128KB)

# Defaults for queryset broadcasts (see WebSocketSessionQuerySet.send_message).
BROADCAST_MAX_WORKERS = 10
BROADCAST_CONNECT_TIMEOUT = 5  # seconds
BROADCAST_READ_TIMEOUT = 10  # seconds
BROADCAST_MAX_ATTEMPTS = 3

# Timeouts for the calls that provision and sync an API Gateway. Without them botocore waits
# 60 seconds to connect and 60 to read, with retries, while a database transaction may be open.
AWS_CONNECT_TIMEOUT = 5  # seconds
AWS_READ_TIMEOUT = 20  # seconds
AWS_MAX_ATTEMPTS = 3

# Connection attempts are kept this long. Recording an attempt deletes expired rows once in
# RATE_LIMIT_PURGE_ONE_IN times, at most RATE_LIMIT_PURGE_BATCH at a time, so the table stays
# bounded even when ``cleanupWebSocketTokens`` is never scheduled.
RATE_LIMIT_RETENTION_DAYS = 7
RATE_LIMIT_PURGE_ONE_IN = 100
RATE_LIMIT_PURGE_BATCH = 500

logger = logging.getLogger(__name__)


# API Gateway adds this header, with a static secret, to every request it sends to Django
# (see WEBSOCKETS["gateway_secret"]). The header is how Django knows a request came from
# the gateway and not from a client that copied the gateway's headers.
GATEWAY_SECRET_HEADER = "X-Ws-Gateway-Secret"

# The secret is written into a static mapping expression, 'value', so it must not contain
# a quote or anything else that could change the expression.
GATEWAY_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{32,}$")


def get_gateway_secrets() -> list[str]:
    """Return the accepted gateway secrets from ``settings.WEBSOCKETS["gateway_secret"]``.

    The setting is a string, or a list of strings to allow a secret to be rotated. The
    first is the one API Gateway is configured to send. An unset or empty setting returns
    an empty list, which turns the check off.
    """
    configured = get_websockets_config().get("gateway_secret")
    if isinstance(configured, str):
        configured = [configured]
    elif not isinstance(configured, (list, tuple)):
        return []
    return [secret for secret in configured if isinstance(secret, str) and secret]


def integration_request_parameters() -> dict:
    """The ``RequestParameters`` for an API Gateway integration that calls Django.

    Always maps the connection ID. Adds the gateway secret header when one is configured.

    :raises ValueError: If the configured secret is too short or has unsafe characters.
    """
    parameters = {"integration.request.header.connectionId": "context.connectionId"}
    secrets_ = get_gateway_secrets()
    if secrets_:
        # fullmatch, because "$" in a pattern also matches before a trailing newline, and a
        # secret read from a file often ends in one
        if not GATEWAY_SECRET_PATTERN.fullmatch(secrets_[0]):
            raise ValueError(
                'WEBSOCKETS["gateway_secret"] must be at least 32 characters from '
                "A-Z a-z 0-9 . _ ~ + / = -, with no newline or other whitespace"
            )
        parameters[f"integration.request.header.{GATEWAY_SECRET_HEADER}"] = (
            f"'{secrets_[0]}'"
        )
    return parameters


def serialise_message(data: dict) -> str:
    """Serialise ``data`` to JSON, raising ``ValueError`` if it exceeds the AWS limit.

    Uses :class:`~django.core.serializers.json.DjangoJSONEncoder`, so lazy translation
    strings, dates, times, ``Decimal`` and ``UUID`` values serialise as well as plain data.
    """
    message_data = json.dumps(data, cls=DjangoJSONEncoder)
    message_size = len(message_data.encode("utf-8"))
    if message_size > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message exceeds AWS limit: {message_size} bytes (max: {MAX_MESSAGE_SIZE} bytes)"
        )
    return message_data


def _post_to_connection(client, message: str, connection_id: str):
    """Post ``message`` to one connection without raising on delivery failures.

    :returns: ``("sent", response)``, ``("gone", None)`` when the client has
        disconnected, or ``("failed", None)`` for any other AWS or network error
        (which is logged).
    """
    try:
        return "sent", client.post_to_connection(
            Data=message, ConnectionId=connection_id
        )
    except ClientError as error:
        code = error.response["Error"]["Code"]
        if code == "GoneException":
            return "gone", None
        logger.warning("Broadcast to connection %s failed: %s", connection_id, code)
    except BotoCoreError:
        logger.warning(
            "Broadcast to connection %s failed", connection_id, exc_info=True
        )
    return "failed", None


def hash_session_key(session_key: str) -> str:
    """Return a keyed hash of a Django session key, for storing in ``WebSocketToken``.

    A session key is a login credential until its session expires, so it is never
    stored. The hash is 64 hexadecimal characters.
    """
    return salted_hmac(
        "django_aws_api_gateway_websockets.WebSocketToken.session_key",
        session_key,
        algorithm="sha256",
    ).hexdigest()


def hash_user_auth(user) -> str:
    """Return a keyed hash of a user's Django session authentication hash.

    The value changes when the user's password changes, so a ``WebSocketSession`` that
    stored it can tell that the login it was opened under no longer holds. It is empty
    for a user model without ``get_session_auth_hash()``.
    """
    get_auth_hash = getattr(user, "get_session_auth_hash", None)
    if get_auth_hash is None:
        return ""
    return salted_hmac(
        "django_aws_api_gateway_websockets.WebSocketSession.auth_hash",
        get_auth_hash(),
        algorithm="sha256",
    ).hexdigest()


def _host_is_allowed(url: str) -> bool:
    """Whether ``url`` points at a host that ``allowed_integration_hosts`` lists.

    Always ``True`` when the setting is empty. A ``*.`` entry matches sub-domains only.
    """
    allowed = get_allowed_integration_hosts()
    if not allowed:
        return True
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower()
    for entry in allowed:
        if entry.startswith("*."):
            if host.endswith(entry[1:]) and len(host) > len(entry) - 1:
                return True
        elif host == entry:
            return True
    return False


def validate_integration_host(url: str, field: str) -> None:
    """Raise a ``ValidationError`` on ``field`` if ``url`` is not at an allowed host.

    The integration URL decides where API Gateway sends every connect, disconnect and message
    event, with the connection ID and the gateway secret. The message does not list the
    allowed hosts.
    """
    if url and not _host_is_allowed(url):
        raise ValidationError(
            {field: _('This host is not in WEBSOCKETS["allowed_integration_hosts"].')}
        )


def _push_enabled(push_to_aws) -> bool:
    """Whether a save or delete should also change AWS.

    An explicit ``push_to_aws`` argument wins. Otherwise ``WEBSOCKETS["push_changes_to_aws"]``
    decides, and it is on by default.
    """
    if push_to_aws is None:
        return get_boolean_setting("push_changes_to_aws")
    return bool(push_to_aws)


_deferred_sync_errors: ContextVar = ContextVar("deferred_sync_errors", default=None)


@contextmanager
def collect_deferred_sync_errors():
    """Collect the ``ApiGatewaySyncError`` of AWS calls that run when a transaction commits.

    The Django admin uses it: it wraps each view in a transaction, so the AWS calls of the
    records it saves run as the view finishes, and it reports each failure as a message.
    Yields a list that fills as the transaction commits, inside the ``with`` block.
    """
    errors: list = []
    token = _deferred_sync_errors.set(errors)
    try:
        yield errors
    finally:
        _deferred_sync_errors.reset(token)


def run_aws_after_commit(operation) -> None:
    """Run an AWS call once the open transaction commits, or now when there is none.

    A call made inside a transaction holds its row locks, and the connection, for as long as
    AWS takes to answer. Run after the commit, it holds neither, and a rollback cannot leave
    AWS changed for a record that was never saved.

    With no transaction, ``operation`` runs at once and its ``ApiGatewaySyncError`` reaches
    the caller. Inside one, the error is passed to ``collect_deferred_sync_errors()`` if that
    is active, and otherwise raised when the transaction commits. Either way, the error is
    already logged, and recorded in the API Gateway's ``last_error``.
    """
    connection = transaction.get_connection(router.db_for_write(ApiGateway))
    if not connection.in_atomic_block:
        operation()
        return

    def run() -> None:
        try:
            operation()
        except ApiGatewaySyncError as error:
            errors = _deferred_sync_errors.get()
            if errors is None:
                raise
            errors.append(error)

    transaction.on_commit(run, using=connection.alias)


def get_region_name():
    """Returns the AWS region name from settings.py. Uses AWS_GATEWAY_REGION_NAME first and falls back to
    AWS_REGION_NAME for backwards compatibility.
    """
    if (
        hasattr(settings, "AWS_GATEWAY_REGION_NAME")
        and settings.AWS_GATEWAY_REGION_NAME
    ):
        return settings.AWS_GATEWAY_REGION_NAME
    elif hasattr(settings, "AWS_REGION_NAME") and settings.AWS_REGION_NAME:
        return settings.AWS_REGION_NAME
    else:
        raise RuntimeError(
            "AWS_GATEWAY_REGION_NAME or AWS_REGION_NAME must be set within settings.py"
        )


def _default_client_config() -> Config:
    return Config(
        connect_timeout=AWS_CONNECT_TIMEOUT,
        read_timeout=AWS_READ_TIMEOUT,
        retries={"mode": "standard", "max_attempts": AWS_MAX_ATTEMPTS},
    )


_boto3_clients: dict = {}
_boto3_clients_lock = threading.Lock()


def clear_boto3_client_cache() -> None:
    """Forget the cached boto3 clients, so the next call builds new ones.

    Call it after changing the AWS credential settings while the process is running.
    """
    with _boto3_clients_lock:
        _boto3_clients.clear()


def _client_cache_key(service: str, kwargs: dict) -> tuple:
    """Everything that decides which client is built, so a changed setting builds a new one.

    The process ID is included so a client made before a worker forked is not shared with
    the child.
    """
    options = []
    for name, value in sorted(kwargs.items()):
        if isinstance(value, Config):
            value = repr(sorted(vars(value).items()))
        options.append((name, value))
    return (
        os.getpid(),
        service,
        getattr(settings, "AWS_IAM_PROFILE", None),
        getattr(settings, "AWS_ACCESS_KEY_ID", None),
        getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        getattr(settings, "AWS_GATEWAY_REGION_NAME", None),
        getattr(settings, "AWS_REGION_NAME", None),
        tuple(options),
    )


def get_boto3_client(service: str = "apigatewayv2", **kwargs):
    """Returns the boto3 client to use.

    When running within AWS, if you are using an IAM Role with the service, E.G. on an EC2 instance, you need to
    set AWS_REGION_NAME within settings.py

    Otherwise you can either use a named profile using settings.AWS_IAM_PROFILE or you can set the credentials
    using both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.

    The client has short connect and read timeouts unless you pass your own ``config``. It is
    built once for each process and set of arguments, then reused: boto3 clients can be shared
    between threads, and a role's temporary credentials refresh on their own. After changing
    the credential settings in a running process, call ``clear_boto3_client_cache()``.

    :param str service: apigatewayv2 | apigatewaymanagementapi
    """
    kwargs.setdefault("config", _default_client_config())
    key = _client_cache_key(service, kwargs)
    with _boto3_clients_lock:
        client = _boto3_clients.get(key)
        if client is None:
            # The lock also covers boto3.Session, which is not safe to create in two threads
            client = _build_boto3_client(service, **kwargs)
            _boto3_clients[key] = client
    return client


def _build_boto3_client(service: str, **kwargs):
    if hasattr(settings, "AWS_IAM_PROFILE") and settings.AWS_IAM_PROFILE:
        # Used a named profile where credentials are stored within .aws folder
        session = boto3.Session(profile_name=settings.AWS_IAM_PROFILE)
        client = session.client(service, **kwargs)
    elif (
        hasattr(settings, "AWS_ACCESS_KEY_ID")
        and settings.AWS_ACCESS_KEY_ID
        and hasattr(settings, "AWS_SECRET_ACCESS_KEY")
        and settings.AWS_SECRET_ACCESS_KEY
    ):
        # Use specific access and secret keys
        region = get_region_name()

        client = boto3.client(
            service,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=region,
            **kwargs,
        )
    else:
        # Use the IAM Role of the machine
        region = get_region_name()
        client = boto3.client(service, region_name=region, **kwargs)

    return client


class ApiGateway(models.Model):
    """Stored the API Gateway definitions"""

    class Meta:
        indexes = [
            models.Index(fields=["api_id"]),
            models.Index(fields=["domain_name"]),
            models.Index(fields=["custom_domain_created"]),
            models.Index(fields=["api_created"]),
            models.Index(fields=["created_on"]),
        ]

    def __str__(self) -> str:
        return self.api_name

    def clean(self):
        """Validate fields only when they have values"""
        validate_integration_host(self.target_base_endpoint, "target_base_endpoint")

        # Validate domain_name only if provided
        if self.domain_name:
            domain_pattern = re.compile(
                r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
            )
            if not domain_pattern.match(self.domain_name):
                raise ValidationError({"domain_name": "Invalid domain name format"})

        # Validate api_name only if provided
        if self.api_name:
            api_name_pattern = re.compile(r"^[ a-zA-Z0-9_-]+$")
            if not api_name_pattern.match(self.api_name):
                raise ValidationError(
                    {
                        "api_name": "API name can only contain alphanumeric characters, spaces, hyphens, and underscores"
                    }
                )

    @classmethod
    def from_db(cls, db, field_names, values, *args, **kwargs):
        """Remember the loaded values of the fields that are pushed to AWS."""
        instance = super().from_db(db, field_names, values, *args, **kwargs)
        instance._aws_snapshot = instance._synced_values()
        return instance

    def _synced_values(self) -> dict:
        """The current values of the loaded fields that are pushed to AWS."""
        return {
            name: self.__dict__[name]
            for name in sync.SYNCED_GATEWAY_FIELDS
            if name in self.__dict__
        }

    @property
    def is_deployed(self) -> bool:
        """``True`` once the API exists in AWS and has been deployed."""
        return bool(self.api_created and self.api_id and self.deployment_id)

    def save(self, *args, push_to_aws: bool | None = None, **kwargs):
        """Ensure the trailing slash is saved to the target endpoint, then update AWS.

        The whole record is validated on a full save. A save with ``update_fields`` writes only
        those columns, skips validation and never calls AWS, which is how provisioning records
        its progress.

        If the gateway is deployed and a field that AWS holds has changed, the change is pushed
        to AWS and the stage is deployed again. The record is saved first, so if AWS fails the
        local change is kept and ``ApiGatewaySyncError`` is raised: run the ``Sync to AWS``
        admin action to try again.

        Whether AWS is updated follows ``WEBSOCKETS["push_changes_to_aws"]``, which is on by
        default. With it off, only the local record changes.

        :param push_to_aws: ``False`` saves without calling AWS and ``True`` always updates AWS,
            whatever the setting says. ``None`` follows the setting.
        :raises ApiGatewaySyncError: If AWS rejects the change.
        """
        full_save = kwargs.get("update_fields") is None
        if full_save:
            self.full_clean()

        if self.target_base_endpoint and not self.target_base_endpoint.endswith("/"):
            self.target_base_endpoint = f"{self.target_base_endpoint}/"
        super().save(*args, **kwargs)

        if full_save:
            previous = getattr(self, "_aws_snapshot", {})
            current = self._synced_values()
            self._aws_snapshot = current
            changed = {
                name
                for name, value in current.items()
                if previous.get(name, value) != value
            }
            if changed and self.is_deployed and _push_enabled(push_to_aws):
                run_aws_after_commit(lambda: self.sync_to_aws(fields=changed))

    def sync_to_aws(self, client=None, fields=None) -> list[str]:
        """Write the local values to the deployed API in AWS.

        Updates the API name, description and selection expressions, points the default and
        additional routes at their URLs, creates local routes that are missing in AWS, and
        deploys the stage if anything changed. Routes that exist only in AWS are left alone.

        :param client: A boto3 ``apigatewayv2`` client. One is created if it is not given.
        :param fields: The names of the changed fields. ``None`` compares everything.
        :returns: A sentence for each change made in AWS.
        :raises ValueError: If the API has not been deployed.
        :raises ApiGatewaySyncError: If AWS rejects the change.
        """
        if not self.is_deployed:
            raise ValueError("The API must be deployed before it can be synced to AWS")
        return self._sync(
            lambda client: sync.push_gateway(self, client, fields), client
        )

    def sync_from_aws(self, client=None) -> list[str]:
        """Read the deployed API in AWS into the local records.

        Nothing is deleted locally. A local additional route that is not in AWS is marked as
        not deployed, and a route that exists only in AWS is added locally.

        :param client: A boto3 ``apigatewayv2`` client. One is created if it is not given.
        :returns: A sentence for each change made to the local records.
        :raises ValueError: If the API has not been deployed.
        :raises ApiGatewaySyncError: If AWS cannot be read.
        """
        if not self.is_deployed:
            raise ValueError(
                "The API must be deployed before it can be synced from AWS"
            )
        return self._sync(lambda client: sync.pull_gateway(self, client), client)

    def _sync(self, operation, client) -> list[str]:
        try:
            changes = operation(client or get_boto3_client())
        except (BotoCoreError, ClientError) as error:
            description = sync.describe_error(error)
            logger.error(
                "Syncing API Gateway '%s' failed: %s",
                self.api_name,
                description,
                exc_info=True,
            )
            self._record_error(error)
            raise ApiGatewaySyncError(description) from error
        if self.last_error:
            self._record(last_error="")
        return changes

    class ProvisioningStatus(models.TextChoices):
        """How far provisioning in AWS has got. Each step is recorded as soon as it succeeds."""

        PENDING = "pending", _("Pending")
        CREATING = "creating", _("Creating")
        API_CREATED = "api_created", _("API created")
        ROUTES_CREATED = "routes_created", _("Routes created")
        DEPLOYED = "deployed", _("Deployed")
        DOMAIN_CREATED = "domain_created", _("Custom domain created")
        MAPPED = "mapped", _("Custom domain mapped")

    api_name = models.CharField(max_length=255, unique=True)
    api_description = models.CharField(max_length=255, blank=True, default="")
    default_channel_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Automatically sets the 'channel' on the WebSocketSession record for the connection",
    )
    domain_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The full domain you wish to use for the API endpoint. E.G ws.example.com",
    )
    target_base_endpoint = models.URLField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "The URL on your website where the API Gateway routes will point, including the trailing /, but excluding "
            "the final route/slug portion of the URL."
            " E.G. If your default route will point to https://www.example.com/ws/default then enter "
            "https://www.example.com/ws/"
        ),
    )
    certificate_arn = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The ARN of the certificate to use from AWS Certificate Manager",
    )
    hosted_zone_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="The Hosted Zone ID from AWs Route 53 for the domain you wish to use",
    )
    api_key_selection_expression = models.CharField(
        max_length=255, default="$request.header.x-api-key"
    )
    route_selection_expression = models.CharField(
        max_length=255, default="$request.body.action"
    )
    route_key = models.CharField(max_length=255, default="$default")
    stage_name = models.CharField(max_length=63, default="production", blank=True)
    stage_description = models.CharField(max_length=63, default="", blank=True)
    deployment_id = models.CharField(
        max_length=32, default="", blank=True, editable=False
    )
    tags = models.JSONField(
        blank=True, default=dict, help_text='In format {"tag-name": "tag-value"}'
    )
    # Returned Values
    api_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="The ID of the Api Gateway returned by AWS",
    )
    api_endpoint = models.CharField(
        max_length=255, blank=True, default="", help_text="The Api Gateway endpoint"
    )
    api_gateway_domain_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The value to point your CNAME record to",
    )
    api_mapping_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="The ApiMappingId to use with api_mapping calls",
    )
    api_created = models.BooleanField(default=False, editable=False)
    custom_domain_created = models.BooleanField(default=False, editable=False)
    provisioning_status = models.CharField(
        max_length=16,
        choices=ProvisioningStatus.choices,
        default=ProvisioningStatus.PENDING,
        help_text=_(
            "How far creating the API in AWS has got. If a run stopped part way, running the "
            "action again continues from here. Change it by hand only to match what exists in "
            "AWS: for example set 'API created' for an API whose routes are missing. 'Creating' "
            "means a run has started, and stays until it records the API. If no run is "
            "active and the API is not in AWS, set 'Pending'."
        ),
    )
    last_error = models.CharField(
        max_length=255,
        blank=True,
        default="",
        editable=False,
        help_text=_("The error that stopped the last provisioning step, if any."),
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    _API_COMPLETE = frozenset(
        {
            ProvisioningStatus.DEPLOYED,
            ProvisioningStatus.DOMAIN_CREATED,
            ProvisioningStatus.MAPPED,
        }
    )

    @property
    def effective_provisioning_status(self) -> str:
        """The status, allowing for records that predate it.

        A record still ``PENDING`` with ``api_created`` set was created before the status
        existed, or was registered by hand for an API that already exists. It is treated as
        complete, because nothing shows how far an older run got and provisioning it again
        could change an API that is in use.
        """
        status = self.provisioning_status
        if status == self.ProvisioningStatus.PENDING and self.api_created:
            if self.custom_domain_created:
                return self.ProvisioningStatus.MAPPED
            return self.ProvisioningStatus.DEPLOYED
        return status

    @property
    def needs_api_creation(self) -> bool:
        """``True`` if the API still has to be created, or finished after a failure."""
        return self.effective_provisioning_status not in self._API_COMPLETE

    @property
    def needs_custom_domain(self) -> bool:
        """``True`` if the API is deployed and the custom domain or its mapping is not done."""
        return self.effective_provisioning_status in (
            self.ProvisioningStatus.DEPLOYED,
            self.ProvisioningStatus.DOMAIN_CREATED,
        )

    def _record(self, **fields) -> None:
        """Set fields and write only those columns, so a step that succeeded is never lost."""
        for name, value in fields.items():
            setattr(self, name, value)
        self.save(update_fields=[*fields, "updated_on"])

    def _record_error(self, error: Exception) -> None:
        """Record why a step stopped. Never raises, so it cannot hide the original error."""
        message = type(error).__name__
        if isinstance(error, ClientError):
            message = f"{message}: {error.response.get('Error', {}).get('Code', '')}"
        try:
            self._record(last_error=message[:255])
        except Exception:
            logger.exception("Could not record the provisioning error")

    def create_gateway(self) -> bool:
        """Creates the actual API gateway record in AWS, or finishes it after a failure

        Each step is recorded as it succeeds (see ``provisioning_status``), so running this
        again after a failure continues from the step that failed. A step that already
        succeeded is not repeated.

        :returns: ``True`` if the gateway was created, ``False`` if it was already complete.
        :raises ValueError: If ``target_base_endpoint`` is not set.
        :raises ValidationError: If the record is invalid. Nothing has been created in AWS.
        """
        if not self.needs_api_creation:
            return False

        if not self.target_base_endpoint:
            raise ValueError(
                "target_base_endpoint is required to create the API Gateway"
            )

        if self.pk is None:
            # Validates the record before anything is created in AWS, so a bad record
            # cannot leave an API behind that nothing points to
            self.save()

        status = self.effective_provisioning_status
        Status = self.ProvisioningStatus
        if status == Status.PENDING:
            self._claim_for_creation()
        elif status == Status.CREATING:
            raise ValueError(self._CREATING_MESSAGE)
        client = get_boto3_client()
        try:
            if status == Status.PENDING:
                self._create_api(client)
                self._record(
                    api_created=True,
                    provisioning_status=Status.API_CREATED,
                    api_id=self.api_id,
                    api_endpoint=self.api_endpoint,
                    last_error="",
                )
                status = Status.API_CREATED
                resumed = False
            else:
                resumed = True

            if status == Status.API_CREATED:
                existing = self._existing_route_keys(client) if resumed else set()
                if resumed:
                    self._create_routes(client, skip_route_keys=existing)
                else:
                    self._create_routes(client)
                if self.pk:
                    for additional_route in self.additional_routes.all():
                        if additional_route.deployed:
                            continue
                        if additional_route.route_key in existing:
                            # Created by an earlier run that stopped part way
                            additional_route._mark_deployed()
                        else:
                            additional_route.create_route(client, deploy=False)
                self._record(provisioning_status=Status.ROUTES_CREATED)
                status = Status.ROUTES_CREATED
                stage_may_exist = False
            else:
                # Resuming here: the stage may exist if the failure came after it was created
                stage_may_exist = True

            if stage_may_exist:
                self._create_stage_and_deploy(client, ignore_existing_stage=True)
            else:
                self._create_stage_and_deploy(client)
            self._record(
                provisioning_status=Status.DEPLOYED,
                deployment_id=self.deployment_id,
                last_error="",
            )
        except Exception as error:
            self._release_claim()
            self._record_error(error)
            raise

        return True

    _CREATING_MESSAGE = (
        "The API is already being created by another request. If no run is active "
        "and the API is not in AWS, set the provisioning status to Pending. If it is "
        "in AWS, set the status to match how far it got."
    )

    def _claim_for_creation(self) -> None:
        """Take the right to create the API in AWS, so two requests cannot both create one.

        One conditional ``UPDATE`` decides the winner, in the database and before AWS is
        called. The request that changes no row is refused.

        :raises ValueError: If another request already holds the claim.
        """
        Status = self.ProvisioningStatus
        claimed = (
            type(self)
            .objects.filter(
                pk=self.pk, provisioning_status=Status.PENDING, api_created=False
            )
            .update(
                provisioning_status=Status.CREATING,
                last_error="",
                updated_on=timezone.now(),
            )
        )
        if not claimed:
            raise ValueError(self._CREATING_MESSAGE)
        self.provisioning_status = Status.CREATING
        self.last_error = ""

    def _release_claim(self) -> None:
        """Give the claim back after a failure that left no API in AWS.

        Once ``create_api`` has returned, an API may exist that the database does not
        record. The claim then stays, so a second run cannot create a duplicate, and a
        person checks AWS. Never raises, so it cannot hide the original error.
        """
        Status = self.ProvisioningStatus
        if self.provisioning_status != Status.CREATING or self.api_id:
            return
        try:
            type(self).objects.filter(
                pk=self.pk, provisioning_status=Status.CREATING
            ).update(provisioning_status=Status.PENDING, updated_on=timezone.now())
            self.provisioning_status = Status.PENDING
        except Exception:
            logger.exception("Could not release the provisioning claim")

    def create_custom_domain(self):
        """Uses boto3 to create the custom domain and associate it with the production stage of the loaded API

        Should be called after create_gateway() has been run. The domain and its mapping are
        recorded as separate steps, so after a failed mapping, running this again creates only
        the mapping.
        :return:
        """
        Status = self.ProvisioningStatus
        status = self.effective_provisioning_status
        if status not in self._API_COMPLETE:
            raise ValueError("The API needs to be created before calling this method")
        if not self.certificate_arn:
            raise ValueError("A Certificate ARN is required")
        if status == Status.MAPPED:
            return

        client = get_boto3_client()
        try:
            if status == Status.DEPLOYED:
                domain_res = self._create_domain_name(client)
                self._record(
                    custom_domain_created=True,
                    provisioning_status=Status.DOMAIN_CREATED,
                    api_gateway_domain_name=domain_res["DomainNameConfigurations"][0][
                        "ApiGatewayDomainName"
                    ],
                    last_error="",
                )
            self._record(
                api_mapping_id=self._create_api_mapping(client),
                provisioning_status=Status.MAPPED,
                last_error="",
            )
        except Exception as error:
            self._record_error(error)
            raise

    def _create_api(self, client):
        """Creates the base API Gateway endpoint"""
        res = client.create_api(
            ApiKeySelectionExpression=self.api_key_selection_expression,
            Description=self.api_description,
            DisableSchemaValidation=True,
            Name=self.api_name,
            ProtocolType="WEBSOCKET",
            RouteKey=self.route_key,
            RouteSelectionExpression=self.route_selection_expression,
            Target=f"{self.target_base_endpoint}default",
        )
        self.api_id = res["ApiId"]
        self.api_endpoint = res["ApiEndpoint"]

    def _existing_route_keys(self, client) -> set:
        """The route keys that already exist on the API in AWS"""
        keys = set()
        token = None
        while True:
            kwargs = {"ApiId": self.api_id}
            if token:
                kwargs["NextToken"] = token
            page = client.get_routes(**kwargs)
            keys.update(item["RouteKey"] for item in page.get("Items", []))
            token = page.get("NextToken")
            if not token:
                return keys

    def _create_routes(self, client, skip_route_keys=frozenset()):
        """Creates the integrations and routes associating the route with integrations

        Route keys in ``skip_route_keys`` already exist, from an earlier run that stopped part way.
        """
        for route in ["$connect", "$disconnect", "$default"]:
            if route in skip_route_keys:
                continue
            integration_res = client.create_integration(
                ApiId=self.api_id,
                ConnectionType="INTERNET",
                IntegrationMethod="POST",
                IntegrationType="HTTP_PROXY",
                IntegrationUri=f"{self.target_base_endpoint}{route.replace('$', '')}",
                PassthroughBehavior="WHEN_NO_MATCH",
                PayloadFormatVersion="1.0",
                RequestParameters=integration_request_parameters(),
                TimeoutInMillis=29000,
            )
            extra_kwargs = {}
            if route == "$default":
                extra_kwargs["RouteResponseSelectionExpression"] = route
            client.create_route(
                ApiId=self.api_id,
                ApiKeyRequired=False,
                AuthorizationType="NONE",
                RouteKey=route,
                Target=f"integrations/{integration_res['IntegrationId']}",
                **extra_kwargs,
            )

    def _create_stage_and_deploy(self, client, ignore_existing_stage=False):
        """Create the stage and deployment

        With ``ignore_existing_stage``, a stage that already exists, from an earlier run that
        stopped before the deployment, is not an error.
        """
        try:
            client.create_stage(ApiId=self.api_id, StageName=self.stage_name)
        except ClientError as error:
            if not (
                ignore_existing_stage
                and error.response.get("Error", {}).get("Code") == "ConflictException"
            ):
                raise
        self.deploy_api(client)

    def deploy_api(self, client):
        res = client.create_deployment(
            ApiId=self.api_id,
            Description=self.stage_description,
            StageName=self.stage_name,
        )
        self.deployment_id = res["DeploymentId"]

    def _create_domain_name(self, client):
        """Creates the domain including the HostedZoneID if one is set"""
        conf = {
            "CertificateArn": self.certificate_arn,
            "DomainNameStatus": "AVAILABLE",
            "EndpointType": "REGIONAL",
            "SecurityPolicy": "TLS_1_2",
        }
        if self.hosted_zone_id:
            conf["HostedZoneId"] = self.hosted_zone_id

        return client.create_domain_name(
            DomainName=self.domain_name, DomainNameConfigurations=[conf]
        )

    def _create_api_mapping(self, client) -> str:
        mapping_res = client.create_api_mapping(
            ApiId=self.api_id, DomainName=self.domain_name, Stage=self.stage_name
        )
        return mapping_res["ApiMappingId"]


class ApiGatewayAdditionalRoute(models.Model):
    """Stores the additional route keys"""

    class Meta:
        # Once version 4 is the minimum supported version then swap to use this
        # constraints = [
        #     models.UniqueConstraint("api_gateway", 'name', name='unique_name_per_gateway')
        # ]
        unique_together = [["api_gateway", "route_key"]]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def from_db(cls, db, field_names, values, *args, **kwargs):
        """Remember the loaded values of the fields that are pushed to AWS."""
        instance = super().from_db(db, field_names, values, *args, **kwargs)
        instance._aws_snapshot = instance._synced_values()
        return instance

    def clean(self):
        """Refuse an integration URL at a host that is not in ``allowed_integration_hosts``"""
        validate_integration_host(self.integration_url, "integration_url")

    def _synced_values(self) -> dict:
        return {
            name: self.__dict__[name]
            for name in ("route_key", "integration_url")
            if name in self.__dict__
        }

    def save(self, *args, push_to_aws: bool | None = None, **kwargs):
        """Save the record, then create or update the route in AWS if the parent is deployed.

        The record is validated first, unless ``update_fields`` is given, so a route cannot be
        saved with an integration URL that is invalid or at a host that is not allowed.

        A new route is always created in AWS, as it was before syncing existed, and at once,
        because the caller needs its AWS IDs. A deployed route whose ``route_key`` or
        ``integration_url`` changed is updated, unless ``WEBSOCKETS["push_changes_to_aws"]`` is
        off. Inside a transaction the update runs when it commits (see
        ``run_aws_after_commit``). The record is saved first, so if AWS fails the local change
        is kept and ``ApiGatewaySyncError`` is raised: run the ``Sync to AWS`` admin action on
        the API gateway to try again. With the setting off, creating a route raises the
        original AWS error.

        :param push_to_aws: ``False`` saves without calling AWS at all and ``True`` always
            updates AWS, whatever the setting says. ``None`` follows the setting.
        :raises ValidationError: If the record is not valid.
        :raises ApiGatewaySyncError: If AWS rejects the change.
        """
        if kwargs.get("update_fields") is None:
            self.full_clean()
        previous = getattr(self, "_aws_snapshot", {})
        super().save(*args, **kwargs)
        current = self._synced_values()
        self._aws_snapshot = current
        if push_to_aws is False or not self.api_gateway.deployment_id:
            return

        push_changes = _push_enabled(push_to_aws)
        if not self.deployed:
            if push_changes:
                self.api_gateway._sync(lambda client: self.create_route(client), None)
            else:
                self.create_route(get_boto3_client())
        elif push_changes and any(
            previous.get(name, value) != value for name, value in current.items()
        ):
            old_key = previous.get("route_key", self.route_key)
            run_aws_after_commit(
                lambda: self.api_gateway._sync(
                    lambda client: self.update_route(
                        client, previous_route_key=old_key
                    ),
                    None,
                )
            )

    api_gateway = models.ForeignKey(
        ApiGateway, on_delete=models.CASCADE, related_name="additional_routes"
    )
    name = models.CharField(max_length=63, help_text="Descriptive name for the route")
    route_key = models.CharField(max_length=64, db_index=True)
    integration_url = models.URLField()
    deployed = models.BooleanField(default=False, editable=False)
    route_id = models.CharField(max_length=32, blank=True, default="", editable=False)
    integration_id = models.CharField(
        max_length=32, blank=True, default="", editable=False
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def create_route(self, client, deploy=True):
        """Create the Integration and then the route"""
        integration_res = client.create_integration(
            ApiId=self.api_gateway.api_id,
            ConnectionType="INTERNET",
            IntegrationMethod="POST",
            IntegrationType="HTTP_PROXY",
            IntegrationUri=self.integration_url,
            PassthroughBehavior="WHEN_NO_MATCH",
            PayloadFormatVersion="1.0",
            RequestParameters=integration_request_parameters(),
            TimeoutInMillis=29000,
        )
        route_res = client.create_route(
            ApiId=self.api_gateway.api_id,
            ApiKeyRequired=False,
            AuthorizationType="NONE",
            RouteKey=self.route_key,
            Target=f"integrations/{integration_res['IntegrationId']}",
            RouteResponseSelectionExpression="$default",
        )

        # Marked once the route exists in AWS. save() is not used, because it would try to
        # create a route that is not marked deployed.
        self._mark_deployed(
            route_res.get("RouteId", ""), integration_res.get("IntegrationId", "")
        )

        if deploy:
            self._deploy(client)

    def update_route(self, client, previous_route_key=None, deploy=True):
        """Point the route in AWS at the current ``integration_url`` and ``route_key``.

        The route is found by its stored ID, or by ``previous_route_key`` when no ID is
        stored. A route that is missing in AWS is created.
        """
        remote = self._find_remote_route(client, previous_route_key or self.route_key)
        if remote is None:
            self.create_route(client, deploy=deploy)
            return

        integration_id = sync.integration_id_of(remote)
        client.update_integration(
            ApiId=self.api_gateway.api_id,
            IntegrationId=integration_id,
            IntegrationUri=self.integration_url,
        )
        if remote["RouteKey"] != self.route_key:
            client.update_route(
                ApiId=self.api_gateway.api_id,
                RouteId=remote["RouteId"],
                RouteKey=self.route_key,
            )
        self._mark_deployed(remote["RouteId"], integration_id)
        if deploy:
            self._deploy(client)

    _aws_deleted = False
    _aws_delete_queued = False

    def delete(self, *args, push_to_aws: bool | None = None, **kwargs):
        """Delete the record, and the route in AWS if the API gateway is deployed.

        Outside a transaction AWS is changed first, so a failure leaves the record in place.
        Inside one, the record is deleted and AWS is changed when the transaction commits, so
        a failure leaves the route in AWS and ``ApiGatewaySyncError`` is raised then. With
        ``WEBSOCKETS["push_changes_to_aws"]`` off, only the record is deleted.

        :param push_to_aws: ``False`` deletes the record without calling AWS and ``True`` always
            deletes the route in AWS, whatever the setting says. ``None`` follows the setting.
        :raises ApiGatewaySyncError: If AWS rejects the change.
        """
        if not _push_enabled(push_to_aws):
            self._aws_deleted = True
        elif transaction.get_connection(
            router.db_for_write(type(self))
        ).in_atomic_block:
            # Inside a transaction the route is removed from AWS once the delete commits
            self._aws_delete_queued = True
            run_aws_after_commit(self._delete_from_aws)
        else:
            self._delete_from_aws()
        return super().delete(*args, **kwargs)

    def _delete_from_aws(self) -> None:
        if self._aws_deleted or not self.deployed:
            return
        gateway = ApiGateway.objects.filter(pk=self.api_gateway_id).first()
        if gateway is None or not gateway.is_deployed:
            return
        self.api_gateway = gateway
        gateway._sync(lambda client: self.delete_route(client), None)
        self._aws_deleted = True

    def delete_route(self, client, deploy=True):
        """Delete the route and its integration from AWS. A route already gone is not an error."""
        remote = self._find_remote_route(client, self.route_key)
        if remote is None:
            return
        api_id = self.api_gateway.api_id
        for call, kwargs in (
            (client.delete_route, {"RouteId": remote["RouteId"]}),
            (
                client.delete_integration,
                {"IntegrationId": sync.integration_id_of(remote)},
            ),
        ):
            try:
                call(ApiId=api_id, **kwargs)
            except ClientError as error:
                if not sync.is_not_found(error):
                    raise
        if deploy:
            self._deploy(client)

    def _find_remote_route(self, client, route_key):
        """The route in AWS, found by its stored ID or else by key, or ``None``"""
        for remote in sync.list_routes(client, self.api_gateway.api_id):
            if remote["RouteId"] == self.route_id or remote["RouteKey"] == route_key:
                return remote
        return None

    def _deploy(self, client) -> None:
        gateway = self.api_gateway
        gateway.deploy_api(client)
        if gateway.pk:
            # deploy_api only sets the ID in memory
            gateway.save(update_fields=["deployment_id", "updated_on"])

    def _mark_deployed(self, route_id: str = "", integration_id: str = "") -> None:
        """Record that the route exists in AWS, writing only the columns that change"""
        self.deployed = True
        values = {"deployed": True, "updated_on": timezone.now()}
        if route_id and isinstance(route_id, str):
            self.route_id = values["route_id"] = route_id
        if integration_id and isinstance(integration_id, str):
            self.integration_id = values["integration_id"] = integration_id
        if self.pk:
            type(self).objects.filter(pk=self.pk).update(**values)


@receiver(pre_delete, sender=ApiGateway)
def disconnect_sessions_of_deleted_gateway(sender, instance, **kwargs):
    """Mark the sessions of an API Gateway disconnected before it is deleted.

    Deleting the gateway sets their ``api_gateway`` to ``NULL``, and a session with no
    gateway cannot be sent to. Left marked connected, it would look live and never receive
    anything.
    """
    WebSocketSession.objects.filter(api_gateway=instance, connected=True).update(
        connected=False, updated_on=timezone.now()
    )


@receiver(user_logged_out)
def close_sessions_on_logout(sender, request=None, **kwargs):
    """Close the WebSocket sessions that were opened under the login that just ended."""
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if not session_key:
        return
    WebSocketSession.objects.filter(
        session_key_hash=hash_session_key(session_key), connected=True
    ).update(connected=False, updated_on=timezone.now())


@receiver(post_delete, sender=ApiGatewayAdditionalRoute)
def delete_route_from_aws(sender, instance, origin=None, **kwargs):
    """Remove a route deleted by a queryset delete from AWS, if the API gateway is deployed.

    ``ApiGatewayAdditionalRoute.delete()`` has already done this for a single route. Only a
    deletion that starts from a route reaches AWS. Deleting the API gateway record, by
    instance, queryset, admin bulk action or a cascade from another model, does not change
    AWS, so its routes are left alone. The queryset delete runs in a transaction, so the AWS
    call runs when it commits. If AWS fails, ``ApiGatewaySyncError`` is raised then, or
    collected by ``collect_deferred_sync_errors()``, and the local delete stays.
    """
    started_from_a_route = isinstance(origin, ApiGatewayAdditionalRoute) or (
        isinstance(origin, models.QuerySet)
        and origin.model is ApiGatewayAdditionalRoute
    )
    if not started_from_a_route or instance._aws_deleted or instance._aws_delete_queued:
        return
    if not get_boolean_setting("push_changes_to_aws"):
        return
    run_aws_after_commit(instance._delete_from_aws)


class WebSocketSessionQuerySet(models.QuerySet):
    def send_message(self, data: dict, max_workers: int = BROADCAST_MAX_WORKERS):
        """Send the same message to all connected WebSocket sessions in the queryset.

        Each session is posted through its own API Gateway, using up to
        ``max_workers`` concurrent requests per gateway. A recipient that fails
        does not stop the others: the failure is logged at ``WARNING`` level on
        the ``django_aws_api_gateway_websockets.models`` logger. Sessions whose
        client has disconnected are marked ``connected=False`` in one query.

        This blocks until every post has finished. Call it from a background task
        rather than a request handler when the channel may be large.

        Example::

            WebSocketSession.objects.filter(
                channel_name="Shared Channel Name",
            ).send_message(
                {
                    "msg": "this is a server sent message",
                }
            )

        :param dict data: The JSON serialisable message.
        :param int max_workers: The maximum number of concurrent posts per gateway.
        :returns: The AWS responses for the posts that succeeded. Failed and
            disconnected recipients are not included.
        :rtype: list
        :raises ValueError: If ``max_workers`` is below 1 or the message exceeds
            the AWS size limit.
        """
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        region = get_region_name()
        msg = serialise_message(data)

        # Group by gateway so each session is posted through its own endpoint,
        # with one client per gateway.
        recipients: dict[tuple[str, str], list[tuple[int, str]]] = {}
        without_gateway = 0
        for pk, connection_id, gateway_id, api_id, stage_name in self.filter(
            connected=True
        ).values_list(
            "pk",
            "connection_id",
            "api_gateway_id",
            "api_gateway__api_id",
            "api_gateway__stage_name",
        ):
            if gateway_id is None:
                without_gateway += 1
                continue
            recipients.setdefault((api_id, stage_name), []).append((pk, connection_id))

        if without_gateway:
            logger.warning(
                "Skipped %d sessions with no API Gateway, so there is no endpoint to "
                "send to. They are still marked connected.",
                without_gateway,
            )

        res = []
        gone_pks = []
        for (api_id, stage_name), sessions in recipients.items():
            workers = min(max_workers, len(sessions))
            client = get_boto3_client(
                "apigatewaymanagementapi",
                endpoint_url=(
                    f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage_name}"
                ),
                config=Config(
                    max_pool_connections=workers,
                    connect_timeout=BROADCAST_CONNECT_TIMEOUT,
                    read_timeout=BROADCAST_READ_TIMEOUT,
                    retries={
                        "mode": "standard",
                        "max_attempts": BROADCAST_MAX_ATTEMPTS,
                    },
                ),
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                outcomes = list(
                    pool.map(
                        partial(_post_to_connection, client, msg),
                        [connection_id for _pk, connection_id in sessions],
                    )
                )
            for (pk, _connection_id), (status, response) in zip(sessions, outcomes):
                if status == "sent":
                    res.append(response)
                elif status == "gone":
                    gone_pks.append(pk)

        if gone_pks:
            self.model._default_manager.filter(pk__in=gone_pks).update(connected=False)

        return res


class WebSocketSession(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=["connection_id", "connected"]),
            models.Index(fields=["channel_name", "connection_id"]),
            models.Index(fields=["channel_name", "connected"]),
        ]

    def __str__(self) -> str:
        return self.connection_id

    def send_message(self, data: dict):
        """Sends a message containing the given data to connection

        :raises ValueError: If the session has no API Gateway, so there is no endpoint to
            post to, or the message exceeds the AWS size limit.
        """
        if self.api_gateway_id is None:
            raise ValueError(
                f"Session {self.connection_id} has no API Gateway to send the message through"
            )
        region = get_region_name()
        # Security: Validate message size before sending
        message_data = serialise_message(data)

        if type(self).api_gateway.is_cached(self):
            gateway = self.api_gateway
        else:
            # Two columns, not the whole row, and not left on the session. Use
            # select_related("api_gateway") when sending to many sessions in a loop.
            gateway = ApiGateway.objects.only("api_id", "stage_name").get(
                pk=self.api_gateway_id
            )

        client = get_boto3_client(
            "apigatewaymanagementapi",
            endpoint_url=(
                f"https://{gateway.api_id}.execute-api."
                f"{region}.amazonaws.com/{gateway.stage_name}"
            ),
        )
        try:
            return client.post_to_connection(
                Data=message_data, ConnectionId=self.connection_id
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "GoneException":
                # Update only the flag, so a stale copy cannot overwrite other fields
                now = timezone.now()
                type(self).objects.filter(pk=self.pk).update(
                    connected=False, updated_on=now
                )
                self.connected = False
                self.updated_on = now
            else:
                raise error

    objects = WebSocketSessionQuerySet.as_manager()

    connection_id = models.CharField(max_length=255, unique=True)
    channel_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Used to group connections together",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        default=None,
        on_delete=models.CASCADE,
        related_name="websocket_sessions",
    )
    connected = models.BooleanField(
        default=True, help_text="Indicates is the connection is current or not"
    )
    api_gateway = models.ForeignKey(
        ApiGateway,
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="sessions",
    )
    request_count = models.PositiveBigIntegerField(default=1)
    # A keyed hash of the Django session key (see hash_session_key), never the key itself.
    # Logging out closes the sessions that carry its hash. Empty when the connection
    # arrived without a Django session.
    session_key_hash = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    # A keyed hash of the user's authentication hash (see hash_user_auth). A password
    # change makes it stop matching, which ends the session. Empty for older rows.
    auth_hash = models.CharField(max_length=64, blank=True, default="")
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)


class WebSocketToken(models.Model):
    """One-time use tokens for establishing WebSocket connections (CSRF protection)"""

    token = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(r"^[a-f0-9]{64}$", "Invalid token format")],
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="websocket_tokens",
    )
    # A keyed hash of the Django session key (see hash_session_key), never the key itself
    session_key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["token", "used"], name="idx_websocket_tokens_used"),
        ]

    @classmethod
    def generate_token(cls, user, session_key):
        """Generate a one-time use WebSocket token"""
        token_value = secrets.token_hex(32)  # 64 character hex string
        return cls.objects.create(
            token=token_value, user=user, session_key=hash_session_key(session_key)
        )

    @classmethod
    def validate_and_consume(cls, token_value, session_key, max_age_seconds=60):
        """Validate token and mark as used (single-use)"""
        try:
            cutoff_time = timezone.now() - timedelta(seconds=max_age_seconds)
            with transaction.atomic():
                token_obj = cls.objects.select_for_update().get(
                    token=token_value,
                    session_key=hash_session_key(session_key),
                    used=False,
                    created_at__gte=cutoff_time,
                )
                # Mark as used immediately
                token_obj.used = True
                token_obj.save(update_fields=["used"])
                return token_obj.user
        except cls.DoesNotExist:
            return None

    @classmethod
    def cleanup_expired(cls, max_age_seconds=300):
        """Delete expired/used tokens (call via cron/celery)"""
        cutoff_time = timezone.now() - timedelta(seconds=max_age_seconds)
        return cls.objects.filter(created_at__lt=cutoff_time).delete()

    @classmethod
    def check_rate_limit(cls, user, max_tokens_per_minute=10):
        """Check if user has exceeded token generation rate limit"""
        one_minute_ago = timezone.now() - timedelta(minutes=1)
        recent_tokens = cls.objects.filter(
            user=user, created_at__gte=one_minute_ago
        ).count()
        return recent_tokens < max_tokens_per_minute


class ConnectionRateLimit(models.Model):
    """Track connection attempts for rate limiting"""

    ip_address = models.GenericIPAddressField(db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="connection_attempts",
    )
    attempt_time = models.DateTimeField(auto_now_add=True, db_index=True)
    successful = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(
                fields=["ip_address", "attempt_time"], name="idx_ip_attempt_time"
            ),
            models.Index(fields=["user", "attempt_time"], name="idx_user_attempt_time"),
        ]

    @classmethod
    def check_rate_limit(cls, ip_address, user=None, max_attempts=20, window_minutes=5):
        """
        Check if IP or user has exceeded connection rate limit

        One query counts the attempts from the IP address and, for an authenticated user,
        the attempts by the user, within the window.

        Returns: (is_allowed: bool, attempts_count: int)
        """
        cutoff_time = timezone.now() - timedelta(minutes=window_minutes)

        counted_user = user if user and user.is_authenticated else None
        by_ip = Q(ip_address=ip_address)
        counts = {"ip": Count("pk", filter=by_ip)}
        matching = by_ip
        if counted_user:
            by_user = Q(user=counted_user)
            counts["user"] = Count("pk", filter=by_user)
            matching = by_ip | by_user

        totals = cls.objects.filter(matching, attempt_time__gte=cutoff_time).aggregate(
            **counts
        )

        ip_attempts = totals["ip"]
        if ip_attempts >= max_attempts:
            return False, ip_attempts

        if counted_user and totals["user"] >= max_attempts:
            return False, totals["user"]

        return True, ip_attempts

    @classmethod
    def record_attempt(cls, ip_address, user=None, successful=False):
        """Record a connection attempt, and now and then delete the expired ones"""
        attempt = cls.objects.create(
            ip_address=ip_address,
            user=user if user and user.is_authenticated else None,
            successful=successful,
        )
        if secrets.randbelow(RATE_LIMIT_PURGE_ONE_IN) == 0:
            try:
                cls._purge_expired()
            except Exception:
                logger.exception("Could not delete expired connection attempts")
        return attempt

    @classmethod
    def _purge_expired(cls) -> int:
        """Delete up to one batch of attempts older than the retention period"""
        cutoff_time = timezone.now() - timedelta(days=RATE_LIMIT_RETENTION_DAYS)
        expired = list(
            cls.objects.filter(attempt_time__lt=cutoff_time).values_list(
                "pk", flat=True
            )[:RATE_LIMIT_PURGE_BATCH]
        )
        if not expired:
            return 0
        return cls.objects.filter(pk__in=expired).delete()[0]

    @classmethod
    def cleanup_old_records(cls, days=RATE_LIMIT_RETENTION_DAYS):
        """Delete old rate limit records (call via cron/celery)"""
        cutoff_time = timezone.now() - timedelta(days=days)
        return cls.objects.filter(attempt_time__lt=cutoff_time).delete()


class ChannelPermission(models.Model):
    """Who may join a WebSocket channel.

    A channel with no row is governed by ``WebSocketView.ALLOW_UNLISTED_CHANNELS``,
    which allows it by default. The default ``WebSocketView.can_join_channel``
    applies the row for the channel being joined.
    """

    class Access(models.TextChoices):
        ALLOW_ALL = "allow_all", _("Allow all")
        SUPERUSER_ONLY = "superuser_only", _("Super admin only")
        STAFF_ONLY = "staff_only", _("Staff only")
        PERMISSIONS = "permissions", _("Requires Django permissions")

    channel_name = models.CharField(
        max_length=128,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-zA-Z0-9_-]+$",
                _("Use only letters, numbers, underscores and hyphens."),
            )
        ],
        help_text=_("The exact channel name this row applies to."),
    )
    access = models.CharField(
        max_length=16,
        choices=Access.choices,
        default=Access.ALLOW_ALL,
        help_text=_(
            "Who may join the channel. The rules below are used only for "
            "'Requires Django permissions'."
        ),
    )
    description = models.CharField(max_length=255, blank=True, default="")
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["channel_name"]

    def __str__(self) -> str:
        return f"{self.channel_name} ({self.get_access_display()})"

    @classmethod
    def for_channel(cls, channel_name: str):
        """Return the row for ``channel_name``, or ``None`` if the channel has none."""
        return cls.objects.filter(channel_name=channel_name).first()

    def allows(self, user) -> bool:
        """Return whether ``user`` may join the channel.

        Anonymous and inactive users are refused by every level except ``ALLOW_ALL``.
        Superusers pass every level. For ``PERMISSIONS`` the user passes if they satisfy
        any one rule, and a rule is satisfied when the user has all of its permissions.
        A channel with no rules, or a rule with no permissions, admits only superusers.
        """
        if self.access == self.Access.ALLOW_ALL:
            return True
        if self.access not in self.Access.values:
            return False
        if user is None or not user.is_authenticated or not user.is_active:
            return False
        if user.is_superuser:
            return True
        if self.access == self.Access.STAFF_ONLY:
            return bool(user.is_staff)
        if self.access == self.Access.PERMISSIONS:
            prefetch_related_objects(
                [self],
                Prefetch(
                    "rules",
                    queryset=ChannelPermissionRule.objects.prefetch_related(
                        Prefetch(
                            "permissions",
                            queryset=Permission.objects.select_related("content_type"),
                        )
                    ),
                ),
            )
            return any(rule.is_satisfied_by(user) for rule in self.rules.all())
        return False


class ChannelPermissionRule(models.Model):
    """One way to satisfy a ``ChannelPermission`` that requires Django permissions.

    The user needs *all* the permissions in a rule (AND). A channel may have several
    rules, and the user needs to satisfy *any* one of them (OR).
    """

    channel_permission = models.ForeignKey(
        ChannelPermission, on_delete=models.CASCADE, related_name="rules"
    )
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="channel_permission_rules",
        help_text=_(
            "The user must have all of these permissions. Add another rule for "
            "an alternative."
        ),
    )

    class Meta:
        ordering = ["pk"]

    @staticmethod
    def _label(permission) -> str:
        return f"{permission.content_type.app_label}.{permission.codename}"

    def __str__(self) -> str:
        labels = [self._label(p) for p in self.permissions.all()]
        return " AND ".join(labels) if labels else str(_("(no permissions)"))

    def is_satisfied_by(self, user) -> bool:
        """Return whether ``user`` has every permission in the rule (never for an empty rule)"""
        labels = [self._label(p) for p in self.permissions.all()]
        return bool(labels) and user.has_perms(labels)
