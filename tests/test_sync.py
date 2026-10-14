from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import SimpleTestCase, TestCase

from django_aws_api_gateway_websockets import sync
from django_aws_api_gateway_websockets.models import (
    ApiGateway,
    ApiGatewayAdditionalRoute,
)
from django_aws_api_gateway_websockets.sync import ApiGatewaySyncError

BASE = "https://www.example.com/ws/"


def client_error(code="NotFoundException"):
    return ClientError({"Error": {"Code": code}}, "Operation")


def fake_client(routes=(), integrations=None, api=None, stage=None):
    """A boto3 client whose AWS side holds the given routes, integrations and API."""
    client = MagicMock()
    client.get_routes.return_value = {"Items": list(routes)}
    client.get_integrations.return_value = {
        "Items": [
            {"IntegrationId": key, "IntegrationUri": uri}
            for key, uri in (integrations or {}).items()
        ]
    }
    client.get_api.return_value = api or {}
    client.get_stage.return_value = stage or {}
    client.get_deployment.return_value = {"Description": ""}
    client.create_deployment.return_value = {"DeploymentId": "d2"}
    return client


def default_aws(base=BASE):
    """The three default routes, each with an integration pointing at ``base``."""
    routes = [
        {"RouteId": f"r{n}", "RouteKey": key, "Target": f"integrations/i{n}"}
        for n, key in enumerate(sync.DEFAULT_ROUTE_KEYS)
    ]
    integrations = {
        f"i{n}": f"{base}{key.replace('$', '')}"
        for n, key in enumerate(sync.DEFAULT_ROUTE_KEYS)
    }
    return routes, integrations


class HelpersSimpleTestCase(SimpleTestCase):
    def test_describe_error_includes_only_the_error_code(self):
        error = ClientError(
            {"Error": {"Code": "BadRequestException", "Message": "secret detail"}}, "Op"
        )
        self.assertEqual("ClientError: BadRequestException", sync.describe_error(error))

    def test_describe_error_names_other_errors(self):
        self.assertEqual("RuntimeError", sync.describe_error(RuntimeError("x")))

    def test_is_not_found(self):
        self.assertTrue(sync.is_not_found(client_error("NotFoundException")))
        self.assertFalse(sync.is_not_found(client_error("ConflictException")))
        self.assertFalse(sync.is_not_found(RuntimeError()))

    def test_integration_id_of(self):
        self.assertEqual("abc", sync.integration_id_of({"Target": "integrations/abc"}))
        self.assertEqual("", sync.integration_id_of({"Target": "other"}))
        self.assertEqual("", sync.integration_id_of({}))

    def test_list_routes_follows_pagination(self):
        client = MagicMock()
        client.get_routes.side_effect = [
            {"Items": [{"RouteId": "a"}], "NextToken": "t"},
            {"Items": [{"RouteId": "b"}]},
        ]
        self.assertEqual(
            ["a", "b"], [r["RouteId"] for r in sync.list_routes(client, "api")]
        )
        self.assertEqual("t", client.get_routes.call_args.kwargs["NextToken"])


class PushGatewaySimpleTestCase(SimpleTestCase):
    def gateway(self, **kwargs):
        gateway = MagicMock(spec=ApiGateway)
        gateway.api_id = "api1"
        gateway.api_name = "New name"
        gateway.api_description = "New description"
        gateway.api_key_selection_expression = "$request.header.x-api-key"
        gateway.route_selection_expression = "$request.body.action"
        gateway.target_base_endpoint = BASE
        gateway.stage_description = ""
        gateway.additional_routes.all.return_value = []
        for name, value in kwargs.items():
            setattr(gateway, name, value)
        return gateway

    def test_a_changed_description_is_pushed_and_deployed(self):
        gateway, client = self.gateway(), fake_client()

        changes = sync.push_gateway(gateway, client, fields={"api_description"})

        client.update_api.assert_called_once_with(
            ApiId="api1", Description="New description"
        )
        gateway.deploy_api.assert_called_once_with(client)
        gateway.save.assert_called_once_with(
            update_fields=["deployment_id", "updated_on"]
        )
        self.assertEqual(["Updated the API Description", "Deployed the stage"], changes)

    def test_a_changed_name_is_pushed(self):
        gateway, client = self.gateway(), fake_client()
        sync.push_gateway(gateway, client, fields={"api_name"})
        client.update_api.assert_called_once_with(ApiId="api1", Name="New name")

    def test_unrelated_fields_do_not_call_aws(self):
        gateway, client = self.gateway(), fake_client()
        self.assertEqual([], sync.push_gateway(gateway, client, fields=set()))
        client.update_api.assert_not_called()
        gateway.deploy_api.assert_not_called()

    def test_a_changed_stage_description_deploys_without_other_calls(self):
        gateway, client = self.gateway(), fake_client()
        changes = sync.push_gateway(gateway, client, fields={"stage_description"})
        client.update_api.assert_not_called()
        gateway.deploy_api.assert_called_once_with(client)
        self.assertEqual(
            ["Updated the stage description", "Deployed the stage"], changes
        )

    def test_a_changed_base_url_repoints_the_three_default_integrations(self):
        routes, integrations = default_aws("https://old.example.com/ws/")
        client = fake_client(routes, integrations)

        changes = sync.push_gateway(
            self.gateway(), client, fields={"target_base_endpoint"}
        )

        uris = {
            c.kwargs["IntegrationId"]: c.kwargs["IntegrationUri"]
            for c in client.update_integration.call_args_list
        }
        self.assertEqual(
            {
                "i0": f"{BASE}connect",
                "i1": f"{BASE}disconnect",
                "i2": f"{BASE}default",
            },
            uris,
        )
        self.assertEqual(4, len(changes))

    def test_a_missing_default_route_is_created(self):
        routes, integrations = default_aws()
        gateway = self.gateway()
        client = fake_client(routes[:2], integrations)

        changes = sync.push_gateway(gateway, client, fields={"target_base_endpoint"})

        gateway._create_routes.assert_called_once_with(
            client, skip_route_keys={"$connect", "$disconnect"}
        )
        self.assertIn("Created the $default route", changes)

    def test_a_full_sync_of_a_matching_gateway_changes_nothing(self):
        routes, integrations = default_aws()
        gateway = self.gateway()
        client = fake_client(
            routes,
            integrations,
            api={
                "Name": "New name",
                "Description": "New description",
                "ApiKeySelectionExpression": "$request.header.x-api-key",
                "RouteSelectionExpression": "$request.body.action",
            },
        )

        self.assertEqual([], sync.push_gateway(gateway, client))

        client.update_api.assert_not_called()
        client.update_integration.assert_not_called()
        gateway.deploy_api.assert_not_called()

    def test_a_full_sync_sends_only_the_api_values_that_differ(self):
        routes, integrations = default_aws()
        client = fake_client(
            routes,
            integrations,
            api={
                "Name": "New name",
                "Description": "Old",
                "ApiKeySelectionExpression": "$request.header.x-api-key",
                "RouteSelectionExpression": "$request.body.action",
            },
        )
        sync.push_gateway(self.gateway(), client)
        client.update_api.assert_called_once_with(
            ApiId="api1", Description="New description"
        )

    def test_additional_routes_are_not_read_for_a_field_change(self):
        gateway = self.gateway()
        sync.push_gateway(gateway, fake_client(), fields={"api_name"})
        gateway.additional_routes.all.assert_not_called()


class PushAdditionalRoutesTestCase(TestCase):
    def setUp(self):
        self.gateway = ApiGateway.objects.create(
            api_name="gw",
            target_base_endpoint=BASE,
            api_id="api1",
            api_created=True,
            deployment_id="d1",
        )
        self.routes, self.integrations = default_aws()
        self.api = {
            "Name": "gw",
            "Description": "",
            "ApiKeySelectionExpression": "$request.header.x-api-key",
            "RouteSelectionExpression": "$request.body.action",
        }

    def make(self, **kwargs):
        route = ApiGatewayAdditionalRoute(
            **{
                "api_gateway": self.gateway,
                "name": "Chat",
                "route_key": "chat",
                "integration_url": f"{BASE}chat",
                "deployed": True,
                **kwargs,
            }
        )
        route.save(push_to_aws=False)
        return route

    def aws(self, extra_routes=(), extra_integrations=None):
        return fake_client(
            [*self.routes, *extra_routes],
            {**self.integrations, **(extra_integrations or {})},
            api=self.api,
        )

    def test_a_route_missing_in_aws_is_created(self):
        route = self.make(deployed=False)
        client = self.aws()
        client.create_integration.return_value = {"IntegrationId": "i9"}
        client.create_route.return_value = {"RouteId": "r9"}

        changes = self.gateway.sync_to_aws(client)

        self.assertIn("Created the chat route", changes)
        route.refresh_from_db()
        self.assertEqual(
            ("r9", "i9", True), (route.route_id, route.integration_id, route.deployed)
        )

    def test_a_changed_url_is_pushed_and_the_ids_are_stored(self):
        route = self.make(integration_url="https://new.example.com/chat")
        remote = {"RouteId": "r9", "RouteKey": "chat", "Target": "integrations/i9"}
        client = self.aws([remote], {"i9": f"{BASE}chat"})

        changes = self.gateway.sync_to_aws(client)

        client.update_integration.assert_called_once_with(
            ApiId="api1",
            IntegrationId="i9",
            IntegrationUri="https://new.example.com/chat",
        )
        self.assertIn("Pointed the chat route at its new URL", changes)
        route.refresh_from_db()
        self.assertEqual(("r9", "i9"), (route.route_id, route.integration_id))

    def test_a_renamed_route_key_is_pushed_using_the_stored_id(self):
        self.make(route_key="chat2", route_id="r9")
        remote = {"RouteId": "r9", "RouteKey": "chat", "Target": "integrations/i9"}
        client = self.aws([remote], {"i9": f"{BASE}chat"})

        self.gateway.sync_to_aws(client)

        client.update_route.assert_called_once_with(
            ApiId="api1", RouteId="r9", RouteKey="chat2"
        )

    def test_routes_only_in_aws_are_left_alone(self):
        remote = {"RouteId": "r9", "RouteKey": "orphan", "Target": "integrations/i9"}
        client = self.aws([remote], {"i9": "https://x/"})

        self.assertEqual([], self.gateway.sync_to_aws(client))

        client.delete_route.assert_not_called()

    def test_a_matching_gateway_is_not_deployed_again(self):
        self.make(route_id="r9", integration_id="i9")
        remote = {"RouteId": "r9", "RouteKey": "chat", "Target": "integrations/i9"}
        client = self.aws([remote], {"i9": f"{BASE}chat"})

        self.assertEqual([], self.gateway.sync_to_aws(client))

        client.create_deployment.assert_not_called()


class PullGatewayTestCase(TestCase):
    def setUp(self):
        self.gateway = ApiGateway.objects.create(
            api_name="gw",
            api_description="local",
            target_base_endpoint=BASE,
            api_id="api1",
            api_created=True,
            deployment_id="d1",
            stage_name="production",
        )
        self.routes, self.integrations = default_aws()

    def aws(self, base=BASE, extra_routes=(), extra_integrations=None, **api):
        routes, integrations = default_aws(base)
        client = fake_client(
            [*routes, *extra_routes],
            {**integrations, **(extra_integrations or {})},
            api={
                "Name": "gw",
                "Description": "local",
                "ApiKeySelectionExpression": "$request.header.x-api-key",
                "RouteSelectionExpression": "$request.body.action",
                "ApiEndpoint": "wss://abc.execute-api.eu-west-1.amazonaws.com",
                **api,
            },
            stage={"DeploymentId": "d1"},
        )
        return client

    def test_remote_values_replace_the_local_ones_without_calling_aws_to_change(self):
        client = self.aws(
            base="https://remote.example.com/ws/", Description="remote", Name="renamed"
        )
        client.get_stage.return_value = {"DeploymentId": "d2"}
        client.get_deployment.return_value = {"Description": "stage text"}

        changes = self.gateway.sync_from_aws(client)

        self.gateway.refresh_from_db()
        self.assertEqual("renamed", self.gateway.api_name)
        self.assertEqual("remote", self.gateway.api_description)
        self.assertEqual(
            "https://remote.example.com/ws/", self.gateway.target_base_endpoint
        )
        self.assertEqual("d2", self.gateway.deployment_id)
        self.assertEqual("stage text", self.gateway.stage_description)
        self.assertTrue(self.gateway.api_endpoint.startswith("wss://"))
        self.assertIn("Updated api_name", changes)
        client.update_api.assert_not_called()
        client.create_deployment.assert_not_called()

    def test_matching_values_report_no_changes(self):
        client = self.aws()
        self.gateway.sync_from_aws(client)  # brings the endpoint and stage in line
        self.assertEqual([], self.gateway.sync_from_aws(client))

    def test_a_missing_stage_leaves_the_deployment_unchanged(self):
        client = self.aws()
        client.get_stage.side_effect = client_error("NotFoundException")
        self.gateway.sync_from_aws(client)
        self.gateway.refresh_from_db()
        self.assertEqual("d1", self.gateway.deployment_id)

    def test_other_stage_errors_are_raised_as_sync_errors(self):
        client = self.aws()
        client.get_stage.side_effect = client_error("TooManyRequestsException")
        with self.assertRaisesMessage(
            ApiGatewaySyncError, "ClientError: TooManyRequestsException"
        ):
            self.gateway.sync_from_aws(client)
        self.gateway.refresh_from_db()
        self.assertEqual(
            "ClientError: TooManyRequestsException", self.gateway.last_error
        )

    def test_a_local_route_takes_the_remote_url_and_key(self):
        route = ApiGatewayAdditionalRoute(
            api_gateway=self.gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://old/",
            deployed=True,
            route_id="r9",
        )
        route.save(push_to_aws=False)
        remote = {"RouteId": "r9", "RouteKey": "chat-new", "Target": "integrations/i9"}
        client = self.aws(
            extra_routes=[remote], extra_integrations={"i9": "https://new/"}
        )

        self.gateway.sync_from_aws(client)

        route.refresh_from_db()
        self.assertEqual(
            ("chat-new", "https://new/"), (route.route_key, route.integration_url)
        )
        self.assertEqual("i9", route.integration_id)

    def test_a_route_only_in_aws_is_added_locally_as_deployed(self):
        remote = {"RouteId": "r9", "RouteKey": "extra", "Target": "integrations/i9"}
        client = self.aws(
            extra_routes=[remote], extra_integrations={"i9": "https://x/"}
        )

        changes = self.gateway.sync_from_aws(client)

        route = self.gateway.additional_routes.get()
        self.assertEqual(
            ("extra", "https://x/", True, "r9"),
            (route.route_key, route.integration_url, route.deployed, route.route_id),
        )
        self.assertIn("Added the extra route", changes)
        client.create_route.assert_not_called()

    def test_a_local_route_missing_in_aws_is_kept_and_marked_not_deployed(self):
        route = ApiGatewayAdditionalRoute(
            api_gateway=self.gateway,
            name="Gone",
            route_key="gone",
            integration_url="https://gone/",
            deployed=True,
            route_id="r9",
        )
        route.save(push_to_aws=False)

        changes = self.gateway.sync_from_aws(self.aws())

        route.refresh_from_db()
        self.assertFalse(route.deployed)
        self.assertEqual("", route.route_id)
        self.assertTrue(any("gone" in change for change in changes))

    def test_sync_methods_need_a_deployed_gateway(self):
        gateway = ApiGateway(api_name="x", api_created=True, api_id="a")
        with self.assertRaises(ValueError):
            gateway.sync_to_aws(MagicMock())
        with self.assertRaises(ValueError):
            gateway.sync_from_aws(MagicMock())

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_client_is_created_when_none_is_given(self, mocked_get_client):
        mocked_get_client.return_value = self.aws()
        self.gateway.sync_from_aws()
        mocked_get_client.assert_called_once_with()

    def test_a_successful_sync_clears_the_last_error(self):
        ApiGateway.objects.filter(pk=self.gateway.pk).update(last_error="old")
        self.gateway.refresh_from_db()
        self.gateway.sync_from_aws(self.aws())
        self.gateway.refresh_from_db()
        self.assertEqual("", self.gateway.last_error)


class PushStageDescriptionTestCase(SimpleTestCase):
    def gateway(self, description):
        gateway = MagicMock(spec=ApiGateway)
        gateway.api_id = "api1"
        gateway.stage_name = "production"
        gateway.stage_description = description
        gateway.target_base_endpoint = None
        gateway.additional_routes.all.return_value = []
        for name in sync.API_FIELDS:
            setattr(gateway, name, "v")
        return gateway

    def aws(self):
        client = fake_client(
            api={aws: "v" for aws in sync.API_FIELDS.values()},
            stage={"DeploymentId": "d1"},
        )
        client.get_deployment.return_value = {"Description": "old"}
        return client

    def test_a_full_sync_deploys_a_changed_stage_description(self):
        gateway = self.gateway("new")
        changes = sync.push_gateway(gateway, self.aws())
        self.assertEqual(
            ["Updated the stage description", "Deployed the stage"], changes
        )
        gateway.deploy_api.assert_called_once()

    def test_a_full_sync_with_the_same_stage_description_changes_nothing(self):
        self.assertEqual([], sync.push_gateway(self.gateway("old"), self.aws()))
