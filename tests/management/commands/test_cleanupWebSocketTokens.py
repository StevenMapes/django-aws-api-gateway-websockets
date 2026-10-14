from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


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


class CleanupTokenAgeFollowsExpiryTestCase(SimpleTestCase):
    """The default age must never delete a token that is still valid."""

    def _run(self, *args):
        with (
            patch(
                "django_aws_api_gateway_websockets.management.commands.cleanupWebSocketTokens.ConnectionRateLimit.cleanup_old_records",
                return_value=(0, {}),
            ),
            patch(
                "django_aws_api_gateway_websockets.management.commands.cleanupWebSocketTokens.WebSocketToken.cleanup_expired",
                return_value=(0, {}),
            ) as mocked_cleanup,
        ):
            call_command("cleanupWebSocketTokens", *args, stdout=StringIO())
        return mocked_cleanup

    @override_settings(WEBSOCKETS={"token_expiry_seconds": 900})
    def test_default_age_is_not_shorter_than_a_longer_expiry(self):
        self._run().assert_called_with(max_age_seconds=900)

    @override_settings(WEBSOCKETS={"token_expiry_seconds": 60})
    def test_default_age_is_at_least_five_minutes(self):
        self._run().assert_called_with(max_age_seconds=300)

    @override_settings(WEBSOCKETS={"token_expiry_seconds": 900})
    def test_an_explicit_age_is_used_as_given(self):
        self._run("--token-age=120").assert_called_with(max_age_seconds=120)
