from botocore.exceptions import ClientError
from django.core.management.base import BaseCommand, CommandError

from django_aws_api_gateway_websockets.models import (
    GATEWAY_SECRET_HEADER,
    ApiGateway,
    get_boto3_client,
    integration_request_parameters,
)

SECRET_PARAMETER = f"integration.request.header.{GATEWAY_SECRET_HEADER}"
CONNECTION_PARAMETER = "integration.request.header.connectionId"


class Command(BaseCommand):
    """Brings the integrations of already deployed API Gateways in line with the gateway secret.

    With ``WEBSOCKETS["gateway_secret"]`` set, API Gateway is changed to send the secret
    on every request. With it unset, the secret header is removed again. Only integrations
    that map ``connectionId``, which are the ones this package creates, are changed.
    """

    help = (
        "Add, change or remove the gateway secret header on the integrations of "
        "deployed API Gateways, then deploy the stage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pk",
            type=int,
            help="Only update the ApiGateway record with this primary key",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without calling AWS to change it",
        )

    def handle(self, *args, **options):
        try:
            desired = integration_request_parameters()
        except ValueError as error:
            raise CommandError(str(error)) from error

        gateways = ApiGateway.objects.filter(api_created=True)
        if options["pk"] is not None:
            gateways = ApiGateway.objects.filter(api_created=True, pk=options["pk"])

        failed = []
        for gateway in gateways.order_by("pk"):
            try:
                self._update_gateway(gateway, desired, options["dry_run"])
            except ClientError as error:
                code = error.response["Error"]["Code"]
                self.stderr.write(f"{gateway.api_name}: AWS returned {code}")
                failed.append(gateway.api_name)

        if failed:
            raise CommandError(f"Failed for: {', '.join(failed)}")

    def _integrations(self, client, api_id):
        token = None
        while True:
            kwargs = {"ApiId": api_id, "MaxResults": "100"}
            if token:
                kwargs["NextToken"] = token
            page = client.get_integrations(**kwargs)
            yield from page.get("Items", [])
            token = page.get("NextToken")
            if not token:
                return

    def _update_gateway(self, gateway, desired, dry_run):
        client = get_boto3_client()
        changed = 0

        for integration in self._integrations(client, gateway.api_id):
            current = integration.get("RequestParameters") or {}
            if CONNECTION_PARAMETER not in current:
                continue  # Not an integration this package created

            wanted = {k: v for k, v in current.items() if k != SECRET_PARAMETER}
            wanted.update(desired)
            if wanted == current:
                self.stdout.write(
                    f"{gateway.api_name}: {integration['IntegrationId']} is up to date"
                )
                continue

            changed += 1
            if dry_run:
                self.stdout.write(
                    f"{gateway.api_name}: would update {integration['IntegrationId']}"
                )
                continue

            client.update_integration(
                ApiId=gateway.api_id,
                IntegrationId=integration["IntegrationId"],
                RequestParameters=wanted,
            )
            self.stdout.write(
                f"{gateway.api_name}: updated {integration['IntegrationId']}"
            )

        if changed and not dry_run:
            # API Gateway applies integration changes only when the stage is deployed
            gateway.deploy_api(client)
            gateway.save()
            self.stdout.write(f"{gateway.api_name}: deployed")
