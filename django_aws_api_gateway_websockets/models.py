import json
import logging
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _

from django_aws_api_gateway_websockets import sync
from django_aws_api_gateway_websockets.conf import (
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
    """Serialise ``data`` to JSON, raising ``ValueError`` if it exceeds the AWS limit."""
    message_data = json.dumps(data)
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


def _push_enabled(push_to_aws) -> bool:
    """Whether a save or delete should also change AWS.

    An explicit ``push_to_aws`` argument wins. Otherwise ``WEBSOCKETS["push_changes_to_aws"]``
    decides, and it is on by default.
    """
    if push_to_aws is None:
        return get_boolean_setting("push_changes_to_aws")
    return bool(push_to_aws)


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


def get_boto3_client(service: str = "apigatewayv2", **kwargs):
    """Returns the boto3 client to use.

    When running within AWS, if you are using an IAM Role with the service, E.G. on an EC2 instance, you need to
    set AWS_REGION_NAME within settings.py

    Otherwise you can either use a named profile using settings.AWS_IAM_PROFILE or you can set the credentials
    using both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.

    :param str service: apigatewayv2 | apigatewaymanagementapi
    """
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
        from django.core.exceptions import ValidationError

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
                self.sync_to_aws(fields=changed)

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
            "AWS: for example set 'API created' for an API whose routes are missing."
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
            self._record_error(error)
            raise

        return True

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

    def _synced_values(self) -> dict:
        return {
            name: self.__dict__[name]
            for name in ("route_key", "integration_url")
            if name in self.__dict__
        }

    def save(self, *args, push_to_aws: bool | None = None, **kwargs):
        """Save the record, then create or update the route in AWS if the parent is deployed.

        A new route is always created in AWS, as it was before syncing existed. A deployed route
        whose ``route_key`` or ``integration_url`` changed is updated, unless
        ``WEBSOCKETS["push_changes_to_aws"]`` is off. The record is saved first, so if AWS fails
        the local change is kept and ``ApiGatewaySyncError`` is raised: run the ``Sync to AWS``
        admin action on the API gateway to try again. With the setting off, creating a route
        raises the original AWS error.

        :param push_to_aws: ``False`` saves without calling AWS at all and ``True`` always
            updates AWS, whatever the setting says. ``None`` follows the setting.
        :raises ApiGatewaySyncError: If AWS rejects the change.
        """
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
            self.api_gateway._sync(
                lambda client: self.update_route(client, previous_route_key=old_key),
                None,
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

    def delete(self, *args, push_to_aws: bool | None = None, **kwargs):
        """Delete the record, and the route in AWS if the API gateway is deployed.

        AWS is changed first, so a failure leaves the record in place. With
        ``WEBSOCKETS["push_changes_to_aws"]`` off, only the record is deleted.

        :param push_to_aws: ``False`` deletes the record without calling AWS and ``True`` always
            deletes the route in AWS, whatever the setting says. ``None`` follows the setting.
        :raises ApiGatewaySyncError: If AWS rejects the change.
        """
        if _push_enabled(push_to_aws):
            self._delete_from_aws()
        else:
            self._aws_deleted = True
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


@receiver(post_delete, sender=ApiGatewayAdditionalRoute)
def delete_route_from_aws(sender, instance, origin=None, **kwargs):
    """Remove a route deleted by a queryset delete from AWS, if the API gateway is deployed.

    ``ApiGatewayAdditionalRoute.delete()`` has already done this for a single route. Deleting
    the whole API gateway record does not change AWS, so its routes are left alone. If AWS
    fails, ``ApiGatewaySyncError`` is raised and the deletion is rolled back.
    """
    if isinstance(origin, ApiGateway) or instance._aws_deleted:
        return
    if not get_boolean_setting("push_changes_to_aws"):
        return
    instance._delete_from_aws()


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
        for pk, connection_id, api_id, stage_name in self.filter(
            connected=True
        ).values_list(
            "pk", "connection_id", "api_gateway__api_id", "api_gateway__stage_name"
        ):
            recipients.setdefault((api_id, stage_name), []).append((pk, connection_id))

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
        """Sends a message containing the given data to connection"""
        region = get_region_name()
        # Security: Validate message size before sending
        message_data = serialise_message(data)

        client = get_boto3_client(
            "apigatewaymanagementapi",
            endpoint_url=(
                f"https://{self.api_gateway.api_id}.execute-api."
                f"{region}.amazonaws.com/{self.api_gateway.stage_name}"
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
        Returns: (is_allowed: bool, attempts_count: int)
        """
        cutoff_time = timezone.now() - timedelta(minutes=window_minutes)

        # Check IP-based rate limit
        ip_attempts = cls.objects.filter(
            ip_address=ip_address, attempt_time__gte=cutoff_time
        ).count()

        if ip_attempts >= max_attempts:
            return False, ip_attempts

        # Check user-based rate limit if user provided
        if user and user.is_authenticated:
            user_attempts = cls.objects.filter(
                user=user, attempt_time__gte=cutoff_time
            ).count()

            if user_attempts >= max_attempts:
                return False, user_attempts

        return True, ip_attempts

    @classmethod
    def record_attempt(cls, ip_address, user=None, successful=False):
        """Record a connection attempt"""
        return cls.objects.create(
            ip_address=ip_address,
            user=user if user and user.is_authenticated else None,
            successful=successful,
        )

    @classmethod
    def cleanup_old_records(cls, days=7):
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
