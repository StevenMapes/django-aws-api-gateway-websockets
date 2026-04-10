from django.core.management.base import BaseCommand

from django_aws_api_gateway_websockets.models import WebSocketToken, ConnectionRateLimit


class Command(BaseCommand):
    help = 'Cleanup expired WebSocket tokens and old rate limit records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--token-age',
            type=int,
            default=300,
            help='Delete tokens older than this many seconds (default: 300 = 5 minutes)',
        )
        parser.add_argument(
            '--rate-limit-age',
            type=int,
            default=7,
            help='Delete rate limit records older than this many days (default: 7)',
        )

    def handle(self, *args, **options):
        token_age = options['token_age']
        rate_limit_age = options['rate_limit_age']

        # Cleanup expired tokens
        token_count, _ = WebSocketToken.cleanup_expired(max_age_seconds=token_age)
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully deleted {token_count} expired WebSocket tokens (older than {token_age}s)'
            )
        )

        # Cleanup old rate limit records
        rate_limit_count, _ = ConnectionRateLimit.cleanup_old_records(days=rate_limit_age)
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully deleted {rate_limit_count} old rate limit records (older than {rate_limit_age} days)'
            )
        )