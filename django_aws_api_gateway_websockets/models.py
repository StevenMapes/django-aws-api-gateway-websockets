import json

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import models


def get_boto3_client(service: str = "apigatewayv2", **kwargs):
    """Returns the boto3 client to use.

    :param str servivce: apigatewayv2 | apigatewaymanagementapi

    If you are using an IAM Role then you just need to set AWS_REGION_NAME within settings.py otherwise you need to
    set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY as well with the correct values
    """
    if (
        hasattr(settings, "AWS_ACCESS_KEY_ID")
        and settings.AWS_ACCESS_KEY_ID
        and hasattr(settings, "AWS_SECRET_ACCESS_KEY")
        and settings.AWS_SECRET_ACCESS_KEY
    ):
        if not hasattr(settings, "AWS_REGION_NAME") or not settings.AWS_REGION_NAME:
            raise RuntimeError("AWS_REGION_NAME must be set within settings.py")

        client = boto3.client(
            service,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME,
            **kwargs,
        )
    else:
        if not hasattr(settings, "AWS_REGION_NAME") or not settings.AWS_REGION_NAME:
            raise RuntimeError("AWS_REGION_NAME must be set within settings.py")
        client = boto3.client(service, region_name=settings.AWS_REGION_NAME, **kwargs)

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

    def save(self, **kwargs):
        """Ensure the trailing slash is saved to the target endpoint"""
        if not self.target_base_endpoint[-1:] == "/":
            self.target_base_endpoint = f"{self.target_base_endpoint}/"
        super().save(**kwargs)

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
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def create_gateway(self):
        """Creates the actual API gateway record"""
        if self.api_created:
            return

        client = get_boto3_client()
        self._create_api(client)
        try:
            self._create_routes(client)
            if self.pk:
                for additional_route in self.additional_routes.all():
                    if not additional_route.deployed:
                        additional_route.create_route(client, deploy=False)
            self._create_stage_and_deploy(client)
        except ClientError as ce:
            raise ce
        finally:
            self.api_created = True
            self.save()

    def create_custom_domain(self):
        """Uses boto3 to create the custom domain and associate it with the production stage of the loaded API

        Should be called after create_gateway() has been run
        :return:
        """
        if not self.api_created:
            raise ValueError("The API needs to be created before calling this method")
        if not self.certificate_arn:
            raise ValueError("A Certificate ARN is required")

        client = get_boto3_client()
        domain_res = self._create_domain_name(client)
        try:
            self.api_gateway_domain_name = domain_res["DomainNameConfigurations"][0][
                "ApiGatewayDomainName"
            ]
            self.api_mapping_id = self._create_api_mapping(client)
        except ClientError as ce:
            raise ce
        finally:
            self.custom_domain_created = True
            self.save()

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
            Target=f"{self.target_base_endpoint}/default",
        )
        self.api_id = res["ApiId"]
        self.api_endpoint = res["ApiEndpoint"]

    def _create_routes(self, client):
        """Creates the integrations and routes associating the route with integrations"""
        for route in ["$connect", "$disconnect", "$default"]:
            integration_res = client.create_integration(
                ApiId=self.api_id,
                ConnectionType="INTERNET",
                IntegrationMethod="POST",
                IntegrationType="HTTP_PROXY",
                IntegrationUri=f"{self.target_base_endpoint}{route.replace('$', '')}",
                PassthroughBehavior="WHEN_NO_MATCH",
                PayloadFormatVersion="1.0",
                RequestParameters={
                    "integration.request.header.connectionId": "context.connectionId"
                },
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

    def _create_stage_and_deploy(self, client):
        """Create the stage and deployment"""
        client.create_stage(ApiId=self.api_id, StageName=self.stage_name)
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

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        """Save the record then deploy the new route if the parent has already been deployed"""
        super().save(*args, **kwargs)
        if self.api_gateway.deployment_id and not self.deployed:
            client = get_boto3_client()
            self.create_route(client)

    api_gateway = models.ForeignKey(
        ApiGateway, on_delete=models.CASCADE, related_name="additional_routes"
    )
    name = models.CharField(max_length=63, help_text="Descriptive name for the route")
    route_key = models.CharField(max_length=64, unique=True)
    integration_url = models.URLField()
    deployed = models.BooleanField(default=False, editable=False)
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
            RequestParameters={
                "integration.request.header.connectionId": "context.connectionId"
            },
            TimeoutInMillis=29000,
        )
        client.create_route(
            ApiId=self.api_gateway.api_id,
            ApiKeyRequired=False,
            AuthorizationType="NONE",
            RouteKey=self.route_key,
            Target=f"integrations/{integration_res['IntegrationId']}",
            RouteResponseSelectionExpression="$default",
        )

        if deploy:
            self.api_gateway.deploy_api(client)
            self.deployed = True
            self.save()


class WebSocketSessionQuerySet(models.QuerySet):
    def send_message(self, data: dict):
        """Sends the same message to all WebSocketSessions included within the current filter

        Example use:

        Send a message to all active connections to the "Shared Channel Name" channel

        WebSocketSession.objects.filter(
            channel="Shared Channel Name"
        ).send_message(
            {
                "msg": "this is a server sent message"
            }
        )
        """
        client = None
        msg = json.dumps(data)
        res = []
        for obj in self.filter(connected=True):
            if not client:
                client = get_boto3_client(
                    "apigatewaymanagementapi",
                    endpoint_url=(
                        f"https://{obj.api_gateway.api_id}.execute-api."
                        f"{settings.AWS_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
                    ),
                )
            try:
                res.append(
                    client.post_to_connection(Data=msg, ConnectionId=obj.connection_id)
                )
            except ClientError as error:
                if error.response["Error"]["Code"] == "GoneException":
                    obj.connected = False
                    obj.save()
                else:
                    raise error

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
        client = get_boto3_client(
            "apigatewaymanagementapi",
            endpoint_url=(
                f"https://{self.api_gateway.api_id}.execute-api."
                f"{settings.AWS_REGION_NAME}.amazonaws.com/{self.api_gateway.stage_name}"
            ),
        )
        try:
            return client.post_to_connection(
                Data=json.dumps(data), ConnectionId=self.connection_id
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "GoneException":
                self.connected = False
                self.save()
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
