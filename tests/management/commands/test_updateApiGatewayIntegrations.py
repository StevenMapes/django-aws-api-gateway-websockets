from io import StringIO
from unittest.mock import MagicMock, call, patch

from botocore.exceptions import ClientError
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from django_aws_api_gateway_websockets.models import GATEWAY_SECRET_HEADER

COMMAND = (
    "django_aws_api_gateway_websockets.management.commands.updateApiGatewayIntegrations"
)
SECRET = "s3cr3t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
CONNECTION = "integration.request.header.connectionId"
SECRET_PARAMETER = f"integration.request.header.{GATEWAY_SECRET_HEADER}"


def _integration(integration_id, parameters):
    return {"IntegrationId": integration_id, "RequestParameters": parameters}


class UpdateApiGatewayIntegrationsTestCase(SimpleTestCase):
    def setUp(self):
        self.stdout = StringIO()
        self.client = MagicMock()
        self.gateway = MagicMock(api_id="API1", api_name="One", api_created=True)
        patcher = patch(f"{COMMAND}.get_boto3_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)
        gateway_patcher = patch(f"{COMMAND}.ApiGateway")
        self.MockApiGateway = gateway_patcher.start()
        self.addCleanup(gateway_patcher.stop)
        self.MockApiGateway.objects.filter.return_value.order_by.return_value = [
            self.gateway
        ]

    def _run(self, *args):
        call_command("updateApiGatewayIntegrations", *args, stdout=self.stdout)

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_adds_the_secret_to_integrations_that_lack_it(self):
        self.client.get_integrations.return_value = {
            "Items": [
                _integration("i1", {CONNECTION: "context.connectionId"}),
                _integration("i2", {CONNECTION: "context.connectionId"}),
            ]
        }

        self._run()

        expected = {CONNECTION: "context.connectionId", SECRET_PARAMETER: f"'{SECRET}'"}
        self.client.update_integration.assert_has_calls(
            [
                call(ApiId="API1", IntegrationId="i1", RequestParameters=expected),
                call(ApiId="API1", IntegrationId="i2", RequestParameters=expected),
            ]
        )
        self.gateway.deploy_api.assert_called_once_with(self.client)
        self.gateway.save.assert_called_once_with()

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_skips_integrations_that_are_already_up_to_date(self):
        current = {CONNECTION: "context.connectionId", SECRET_PARAMETER: f"'{SECRET}'"}
        self.client.get_integrations.return_value = {
            "Items": [_integration("i1", current)]
        }

        self._run()

        self.client.update_integration.assert_not_called()
        self.gateway.deploy_api.assert_not_called()
        self.assertIn("up to date", self.stdout.getvalue())

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_replaces_an_old_secret(self):
        old = {CONNECTION: "context.connectionId", SECRET_PARAMETER: "'old-secret'"}
        self.client.get_integrations.return_value = {"Items": [_integration("i1", old)]}

        self._run()

        self.client.update_integration.assert_called_once_with(
            ApiId="API1",
            IntegrationId="i1",
            RequestParameters={
                CONNECTION: "context.connectionId",
                SECRET_PARAMETER: f"'{SECRET}'",
            },
        )

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_leaves_integrations_the_library_did_not_create_alone(self):
        """Only integrations that map connectionId belong to this library."""
        self.client.get_integrations.return_value = {
            "Items": [
                _integration("other", {"integration.request.header.x": "'1'"}),
                {"IntegrationId": "bare"},
            ]
        }

        self._run()

        self.client.update_integration.assert_not_called()

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_keeps_other_request_parameters(self):
        parameters = {
            CONNECTION: "context.connectionId",
            "integration.request.header.x": "'1'",
        }
        self.client.get_integrations.return_value = {
            "Items": [_integration("i1", parameters)]
        }

        self._run()

        sent = self.client.update_integration.call_args.kwargs["RequestParameters"]
        self.assertEqual("'1'", sent["integration.request.header.x"])
        self.assertEqual(f"'{SECRET}'", sent[SECRET_PARAMETER])

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_follows_pagination(self):
        self.client.get_integrations.side_effect = [
            {
                "Items": [_integration("i1", {CONNECTION: "context.connectionId"})],
                "NextToken": "t",
            },
            {"Items": [_integration("i2", {CONNECTION: "context.connectionId"})]},
        ]

        self._run()

        self.assertEqual(2, self.client.update_integration.call_count)
        self.assertEqual(
            "t", self.client.get_integrations.call_args_list[1].kwargs["NextToken"]
        )

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_dry_run_changes_nothing(self):
        self.client.get_integrations.return_value = {
            "Items": [_integration("i1", {CONNECTION: "context.connectionId"})]
        }

        self._run("--dry-run")

        self.client.update_integration.assert_not_called()
        self.gateway.deploy_api.assert_not_called()
        self.assertIn("i1", self.stdout.getvalue())
        self.assertNotIn(SECRET, self.stdout.getvalue())

    @override_settings(WEBSOCKETS=None)
    def test_removes_the_secret_when_none_is_configured(self):
        """Lets a deployment switch the feature off again."""
        current = {CONNECTION: "context.connectionId", SECRET_PARAMETER: "'old'"}
        self.client.get_integrations.return_value = {
            "Items": [_integration("i1", current)]
        }

        self._run()

        self.client.update_integration.assert_called_once_with(
            ApiId="API1",
            IntegrationId="i1",
            RequestParameters={CONNECTION: "context.connectionId"},
        )

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_pk_selects_one_gateway(self):
        self.client.get_integrations.return_value = {"Items": []}

        self._run("--pk=7")

        self.MockApiGateway.objects.filter.assert_called_with(api_created=True, pk=7)

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_without_pk_every_created_gateway_is_used(self):
        self.client.get_integrations.return_value = {"Items": []}

        self._run()

        self.MockApiGateway.objects.filter.assert_called_with(api_created=True)

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_an_aws_error_is_reported_and_other_gateways_still_run(self):
        second = MagicMock(api_id="API2", api_name="Two", api_created=True)
        self.MockApiGateway.objects.filter.return_value.order_by.return_value = [
            self.gateway,
            second,
        ]
        self.client.get_integrations.side_effect = [
            ClientError({"Error": {"Code": "Boom", "Message": "x"}}, "GetIntegrations"),
            {"Items": [_integration("i1", {CONNECTION: "context.connectionId"})]},
        ]

        with self.assertRaises(CommandError):
            self._run()

        self.client.update_integration.assert_called_once()
        self.assertEqual(
            "API2", self.client.update_integration.call_args.kwargs["ApiId"]
        )

    @override_settings(WEBSOCKETS={"gateway_secret": "bad'secret"})
    def test_an_invalid_secret_stops_the_command_before_calling_aws(self):
        with self.assertRaises(CommandError):
            self._run()

        self.client.get_integrations.assert_not_called()
