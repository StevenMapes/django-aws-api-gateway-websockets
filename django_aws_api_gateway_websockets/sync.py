"""Keeps a deployed API Gateway in AWS in line with its local records.

``push_gateway`` writes the local values to AWS and ``pull_gateway`` reads the AWS values
into the local records. Both return a list of plain sentences describing each change, which
is empty when the two sides already match.
"""

import logging
from collections.abc import Iterator

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

DEFAULT_ROUTE_KEYS = ("$connect", "$disconnect", "$default")

# Local ``ApiGateway`` fields that API Gateway holds on the API itself
API_FIELDS = {
    "api_name": "Name",
    "api_description": "Description",
    "api_key_selection_expression": "ApiKeySelectionExpression",
    "route_selection_expression": "RouteSelectionExpression",
}

# Every local field that is pushed to AWS when it changes
SYNCED_GATEWAY_FIELDS = (
    *API_FIELDS,
    "target_base_endpoint",
    "stage_description",
)


class ApiGatewaySyncError(Exception):
    """AWS refused, or could not be reached for, a change to a deployed API Gateway."""


def describe_error(error: Exception) -> str:
    """A short description of an AWS error that is safe to show to a user and to store."""
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "")
        return f"{type(error).__name__}: {code}"
    return type(error).__name__


def is_not_found(error: Exception) -> bool:
    """``True`` if AWS reports the thing asked for does not exist."""
    return (
        isinstance(error, ClientError)
        and error.response.get("Error", {}).get("Code") == "NotFoundException"
    )


def _pages(call, **kwargs) -> Iterator[dict]:
    """Yield every item from a paginated ``get_*`` call."""
    token = None
    while True:
        extra = {"NextToken": token} if token else {}
        page = call(**kwargs, **extra)
        yield from page.get("Items", [])
        token = page.get("NextToken")
        if not token:
            return


def list_routes(client, api_id: str) -> list[dict]:
    """Every route on the API."""
    return list(_pages(client.get_routes, ApiId=api_id, MaxResults="100"))


def list_integrations(client, api_id: str) -> dict[str, dict]:
    """Every integration on the API, by integration ID."""
    items = _pages(client.get_integrations, ApiId=api_id, MaxResults="100")
    return {item["IntegrationId"]: item for item in items}


def integration_id_of(route: dict) -> str:
    """The integration ID a route points to, or an empty string."""
    target = route.get("Target", "")
    prefix = "integrations/"
    return target[len(prefix) :] if target.startswith(prefix) else ""


def _redeploy(gateway, client) -> None:
    gateway.deploy_api(client)
    gateway.save(update_fields=["deployment_id", "updated_on"])


def _remote_stage(gateway, client) -> dict:
    """The ``DeploymentId`` and ``Description`` of the deployment the stage uses.

    Empty if the stage does not exist or has no deployment.
    """
    try:
        stage = client.get_stage(ApiId=gateway.api_id, StageName=gateway.stage_name)
    except ClientError as error:
        if not is_not_found(error):
            raise
        return {}
    deployment_id = stage.get("DeploymentId")
    if not deployment_id:
        return {}
    deployment = client.get_deployment(ApiId=gateway.api_id, DeploymentId=deployment_id)
    return {
        "DeploymentId": deployment_id,
        "Description": deployment.get("Description", ""),
    }


def push_gateway(gateway, client, fields=None) -> list[str]:
    """Write the local values of a deployed gateway to AWS, then deploy if anything changed.

    :param gateway: The ``ApiGateway``. It must already be deployed.
    :param client: A boto3 ``apigatewayv2`` client.
    :param fields: The names of the local fields that changed. ``None`` compares everything,
        including the additional routes, and changes only what differs.
    :returns: A sentence for each change made in AWS.
    """
    full = fields is None
    wanted = set(SYNCED_GATEWAY_FIELDS) if full else set(fields)
    changes: list[str] = []

    api_fields = [name for name in API_FIELDS if name in wanted]
    if api_fields:
        remote_api = client.get_api(ApiId=gateway.api_id) if full else {}
        update = {
            API_FIELDS[name]: getattr(gateway, name)
            for name in api_fields
            if remote_api.get(API_FIELDS[name]) != getattr(gateway, name)
        }
        if update:
            client.update_api(ApiId=gateway.api_id, **update)
            changes.extend(f"Updated the API {key}" for key in update)

    push_endpoints = "target_base_endpoint" in wanted and gateway.target_base_endpoint
    if push_endpoints or full:
        routes = list_routes(client, gateway.api_id)
        integrations = list_integrations(client, gateway.api_id)
        if push_endpoints:
            changes.extend(_push_default_routes(gateway, client, routes, integrations))
        if full:
            changes.extend(
                _push_additional_routes(gateway, client, routes, integrations)
            )

    if full:
        remote_description = _remote_stage(gateway, client).get("Description")
        if remote_description not in (None, gateway.stage_description):
            changes.append("Updated the stage description")
    elif "stage_description" in wanted:
        changes.append("Updated the stage description")

    if changes:
        _redeploy(gateway, client)
        changes.append("Deployed the stage")
    return changes


def _push_default_routes(gateway, client, routes, integrations) -> list[str]:
    changes = []
    by_key = {route["RouteKey"]: route for route in routes}
    for key in DEFAULT_ROUTE_KEYS:
        route = by_key.get(key)
        if route is None:
            continue
        uri = f"{gateway.target_base_endpoint}{key.replace('$', '')}"
        integration_id = integration_id_of(route)
        if integrations.get(integration_id, {}).get("IntegrationUri") == uri:
            continue
        client.update_integration(
            ApiId=gateway.api_id, IntegrationId=integration_id, IntegrationUri=uri
        )
        changes.append(f"Pointed the {key} route at {uri}")

    missing = set(DEFAULT_ROUTE_KEYS) - set(by_key)
    if missing:
        gateway._create_routes(client, skip_route_keys=set(by_key))
        changes.extend(f"Created the {key} route" for key in sorted(missing))
    return changes


def _push_additional_routes(gateway, client, routes, integrations) -> list[str]:
    changes = []
    by_key = {route["RouteKey"]: route for route in routes}
    by_id = {route["RouteId"]: route for route in routes}
    for local in gateway.additional_routes.all():
        remote = by_id.get(local.route_id) or by_key.get(local.route_key)
        if remote is None:
            local.create_route(client, deploy=False)
            changes.append(f"Created the {local.route_key} route")
            continue

        integration_id = integration_id_of(remote)
        if integrations.get(integration_id, {}).get("IntegrationUri") != (
            local.integration_url
        ):
            client.update_integration(
                ApiId=gateway.api_id,
                IntegrationId=integration_id,
                IntegrationUri=local.integration_url,
            )
            changes.append(f"Pointed the {local.route_key} route at its new URL")
        if remote["RouteKey"] != local.route_key:
            client.update_route(
                ApiId=gateway.api_id,
                RouteId=remote["RouteId"],
                RouteKey=local.route_key,
            )
            changes.append(f"Renamed the {remote['RouteKey']} route")
        local._mark_deployed(remote["RouteId"], integration_id)
    return changes


def pull_gateway(gateway, client) -> list[str]:
    """Read a deployed gateway from AWS into the local records.

    Nothing is deleted locally and nothing is changed in AWS. A local route that no longer
    exists in AWS is marked as not deployed, so ``push_gateway`` creates it again.

    :param gateway: The ``ApiGateway``. It must already be deployed.
    :param client: A boto3 ``apigatewayv2`` client.
    :returns: A sentence for each change made to the local records.
    """
    changes: list[str] = []
    changed_fields = []

    remote_api = client.get_api(ApiId=gateway.api_id)
    values = {
        **{name: remote_api.get(aws) for name, aws in API_FIELDS.items()},
        "api_endpoint": remote_api.get("ApiEndpoint"),
    }

    routes = list_routes(client, gateway.api_id)
    integrations = list_integrations(client, gateway.api_id)
    by_key = {route["RouteKey"]: route for route in routes}

    default_route = by_key.get("$default")
    if default_route:
        uri = integrations.get(integration_id_of(default_route), {}).get(
            "IntegrationUri", ""
        )
        if uri.endswith("default"):
            values["target_base_endpoint"] = uri[: -len("default")]

    stage = _remote_stage(gateway, client)
    if stage:
        values["deployment_id"] = stage["DeploymentId"]
        values["stage_description"] = stage["Description"]

    for name, value in values.items():
        if value is not None and getattr(gateway, name) != value:
            setattr(gateway, name, value)
            changed_fields.append(name)
            changes.append(f"Updated {name}")
    if changed_fields:
        # update_fields skips validation and does not push the values straight back to AWS
        gateway.save(update_fields=[*changed_fields, "updated_on"])

    changes.extend(_pull_additional_routes(gateway, routes, integrations))
    return changes


def _pull_additional_routes(gateway, routes, integrations) -> list[str]:
    from django_aws_api_gateway_websockets.models import ApiGatewayAdditionalRoute

    changes = []
    remote_by_id = {}
    for route in routes:
        if route["RouteKey"] not in DEFAULT_ROUTE_KEYS:
            remote_by_id[route["RouteId"]] = route
    remote_by_key = {route["RouteKey"]: route for route in remote_by_id.values()}

    seen = set()
    for local in gateway.additional_routes.all():
        remote = remote_by_id.get(local.route_id) or remote_by_key.get(local.route_key)
        if remote is None:
            if local.deployed:
                ApiGatewayAdditionalRoute.objects.filter(pk=local.pk).update(
                    deployed=False, route_id="", integration_id=""
                )
                changes.append(
                    f"The {local.route_key} route is not in AWS, so it is marked as not deployed"
                )
            continue

        seen.add(remote["RouteId"])
        integration_id = integration_id_of(remote)
        uri = integrations.get(integration_id, {}).get(
            "IntegrationUri", local.integration_url
        )
        values = {
            "route_key": remote["RouteKey"],
            "integration_url": uri,
            "route_id": remote["RouteId"],
            "integration_id": integration_id,
            "deployed": True,
        }
        if any(getattr(local, name) != value for name, value in values.items()):
            ApiGatewayAdditionalRoute.objects.filter(pk=local.pk).update(**values)
            changes.append(f"Updated the {remote['RouteKey']} route")

    for route_id, remote in remote_by_id.items():
        if route_id in seen:
            continue
        integration_id = integration_id_of(remote)
        # What AWS holds is recorded as it is, so the record is not validated: a route
        # the host does not allow is still a route that exists.
        ApiGatewayAdditionalRoute.objects.bulk_create(
            [
                ApiGatewayAdditionalRoute(
                    api_gateway=gateway,
                    name=remote["RouteKey"][:63],
                    route_key=remote["RouteKey"],
                    integration_url=integrations.get(integration_id, {}).get(
                        "IntegrationUri", ""
                    ),
                    route_id=route_id,
                    integration_id=integration_id,
                    deployed=True,
                )
            ]
        )
        changes.append(f"Added the {remote['RouteKey']} route")
    return changes
