from django.conf import settings
from django.db import models


class WebSocketSession(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=["connection_id", "connected"]),
            models.Index(fields=["channel_name", "connection_id"]),
            models.Index(fields=["channel_name", "connected"]),
        ]

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
    request_count = models.PositiveBigIntegerField(default=1)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
