from django.contrib import admin
from django.contrib.admin import ModelAdmin

from django_aws_api_gateway_websockets import models


@admin.register(models.WebSocketSession)
class WebSocketSessionAdmin(ModelAdmin):
    search_fields = ["connection_id", "channel_name"]
    autocomplete_fields = ["user"]
    list_display = [
        "connection_id",
        "channel_name",
        "user",
        "connected",
        "request_count",
        "created_on",
        "updated_on",
    ]
    list_filter = ["connected", "channel_name"]
    date_hierarchy = "created_on"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")
