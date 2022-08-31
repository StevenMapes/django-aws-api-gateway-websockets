from django.core.management.base import BaseCommand

from django_aws_api_gateway_websockets.models import WebSocketSession


class Command(BaseCommand):
    """Removes the dead websocket connections from the table"""

    def handle(self, *args, **options):
        """Removed disconnected websockets"""
        WebSocketSession.objects.filter(connected=False).delete()
