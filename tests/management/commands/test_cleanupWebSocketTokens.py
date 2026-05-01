from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class CleanupWebSocketTokensCommandTestCase(SimpleTestCase):
    @patch(
        "django_aws_api_gateway_websockets.management.commands.cleanupWebSocketTokens.ConnectionRateLimit.cleanup_old_records"
    )
    @patch(
        "django_aws_api_gateway_websockets.management.commands.cleanupWebSocketTokens.WebSocketToken.cleanup_expired"
    )
    def test_handle_uses_default_arguments(
        self,
        mocked_cleanup_expired,
        mocked_cleanup_old_records,
    ):
        mocked_cleanup_expired.return_value = (2, {})
        mocked_cleanup_old_records.return_value = (3, {})
        stdout = StringIO()

        call_command("cleanupWebSocketTokens", stdout=stdout)

        mocked_cleanup_expired.assert_called_with(max_age_seconds=300)
        mocked_cleanup_old_records.assert_called_with(days=7)
        self.assertIn(
            "Successfully deleted 2 expired WebSocket tokens (older than 300s)",
            stdout.getvalue(),
        )
        self.assertIn(
            "Successfully deleted 3 old rate limit records (older than 7 days)",
            stdout.getvalue(),
        )

    @patch(
        "django_aws_api_gateway_websockets.management.commands.cleanupWebSocketTokens.ConnectionRateLimit.cleanup_old_records"
    )
    @patch(
        "django_aws_api_gateway_websockets.management.commands.cleanupWebSocketTokens.WebSocketToken.cleanup_expired"
    )
    def test_handle_uses_custom_arguments(
        self,
        mocked_cleanup_expired,
        mocked_cleanup_old_records,
    ):
        mocked_cleanup_expired.return_value = (4, {})
        mocked_cleanup_old_records.return_value = (5, {})
        stdout = StringIO()

        call_command(
            "cleanupWebSocketTokens",
            token_age=60,
            rate_limit_age=2,
            stdout=stdout,
        )

        mocked_cleanup_expired.assert_called_with(max_age_seconds=60)
        mocked_cleanup_old_records.assert_called_with(days=2)
        self.assertIn(
            "Successfully deleted 4 expired WebSocket tokens (older than 60s)",
            stdout.getvalue(),
        )
        self.assertIn(
            "Successfully deleted 5 old rate limit records (older than 2 days)",
            stdout.getvalue(),
        )
