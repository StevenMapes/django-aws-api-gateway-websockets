from botocore import exceptions
from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin, TabularInline

from django_aws_api_gateway_websockets import models


def create_api_gateway(modeladmin, request, queryset):
    """Creates the API Gateway record if one does not already exist"""
    for obj in queryset:
        if not obj.api_created:
            try:
                obj.create_gateway()
                messages.success(
                    request, f"API Gateway endpoint created for {obj.api_name}"
                )
            except exceptions.ClientError as ce:
                messages.error(
                    request, f"{str(ce)} occurred when processing {obj.api_name}"
                )


create_api_gateway.short_description = "Create API Gateway"


def create_custom_domain(modeladmin, request, queryset):
    """Creates the Custom Domain record if one does not already exist"""
    for obj in queryset:
        if obj.api_created and not obj.custom_domain_created:
            try:
                obj.create_custom_domain()
                messages.success(
                    request,
                    f"Custom Domain setup for {obj.api_name}. Next update DNS to point to {obj.api_gateway_domain_name}",
                )
            except exceptions.ClientError as ce:
                messages.error(
                    request, f"{str(ce)} occurred when processing {obj.api_name}"
                )


create_custom_domain.short_description = "Create Custom Domain record for the API"


class ApiGatewayAdditionalRouteInline(TabularInline):
    autocomplete_fields = ["api_gateway"]
    model = models.ApiGatewayAdditionalRoute
    extra = 1

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_gateway")


@admin.register(models.WebSocketSession)
class WebSocketSessionAdmin(ModelAdmin):
    search_fields = ["connection_id", "channel_name"]
    autocomplete_fields = ["user"]
    list_display = [
        "connection_id",
        "channel_name",
        "api_gateway",
        "user",
        "connected",
        "request_count",
        "created_on",
        "updated_on",
    ]
    list_filter = ["connected", "channel_name"]
    date_hierarchy = "created_on"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "api_gateway")


@admin.register(models.ApiGateway)
class ApiGatewayAdmin(ModelAdmin):
    search_fields = ["domain_name", "api_name"]
    list_display = [
        "api_name",
        "domain_name",
        "default_channel_name",
        "api_id",
        "api_endpoint",
        "api_gateway_domain_name",
        "api_created",
        "custom_domain_created",
        "created_on",
        "updated_on",
    ]
    list_filter = ["api_created", "custom_domain_created"]
    actions = [create_api_gateway, create_custom_domain]
    date_hierarchy = "created_on"
    inlines = [
        ApiGatewayAdditionalRouteInline,
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("additional_routes")


@admin.register(models.ApiGatewayAdditionalRoute)
class ApiGatewayAdditionalRouteAdmin(ModelAdmin):
    autocomplete_fields = ["api_gateway"]
    search_fields = ["name", "key"]
    list_display = ["name", "api_gateway", "route_key", "integration_url", "deployed"]
    list_filter = ["api_gateway"]
    date_hierarchy = "created_on"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_gateway")
