from unittest.mock import patch

from django.test import SimpleTestCase

from django_aws_api_gateway_websockets.management.commands.clearWebSocketSessions import (
    Command,
)


class ClearWebSocketSessionTestCase(SimpleTestCase):
    """Test the management command takes the expected action(s)"""

    @patch(
        "django_aws_api_gateway_websockets.management.commands.clearWebSocketSessions.WebSocketSession"
    )
    def test_handle(self, MockWebSocketSession):
        cmd = Command()
        cmd.handle()
        MockWebSocketSession.objects.filter.assert_called_with(connected=False)
        MockWebSocketSession.objects.filter.return_value.delete.assert_called_with()
