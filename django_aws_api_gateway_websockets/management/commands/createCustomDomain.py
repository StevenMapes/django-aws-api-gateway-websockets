from django.core.management.base import BaseCommand

from django_aws_api_gateway_websockets.models import ApiGateway


class Command(BaseCommand):
    def add_arguments(self, parser):
        """One required argument: pk which determine the ApiGateway object to run"""
        parser.add_argument(
            "--pk",
            required=True,
            type=int,
            help="The PK of the record you wish to run",
        )

    def handle(self, *args, **options):
        """Handles the request"""
        api = ApiGateway.objects.get(
            pk=options["pk"], api_created=True, custom_domain_created=False
        )
        api.create_custom_domain()
