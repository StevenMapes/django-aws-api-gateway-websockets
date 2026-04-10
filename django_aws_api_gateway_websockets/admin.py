import logging

from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin, TabularInline

from .models import ApiGateway, ApiGatewayAdditionalRoute, WebSocketSession, WebSocketToken, ConnectionRateLimit

logger = logging.getLogger(__name__)


@admin.action(
    description="Create API Gateway"
)
def create_api_gateway(modeladmin, request, queryset):
    """Creates the API Gateway record if one does not already exist"""
    for obj in queryset:
        if not obj.api_created:
            try:
                # Security: Audit log administrative actions
                logger.info(
                    f"Admin '{request.user.username}' initiating API Gateway creation for '{obj.api_name}' (ID: {obj.pk})"
                )

                if obj.create_gateway():
                    messages.success(request, f"{obj.api_name} created")
                    logger.info(
                        f"API Gateway '{obj.api_name}' (ID: {obj.pk}) created successfully by '{request.user.username}'"
                    )
                else:
                    messages.info(request, f"{obj.api_name} already created")

            except Exception as e:
                # Security: Log errors without exposing sensitive details to user
                logger.error(
                    f"Failed to create API Gateway '{obj.api_name}' (ID: {obj.pk}) by '{request.user.username}': {str(e)}",
                    exc_info=True
                )
                messages.error(request, f"Failed to create {obj.api_name}: {type(e).__name__}")


@admin.action(description="Create Custom Domain")
def create_custom_domain(self, request, queryset):
    """Using the queryset, call the create_custom_domain method to create a custom domain"""
    for obj in queryset:
        if obj.api_created and not obj.custom_domain_created:
            try:
                # Security: Audit log administrative actions
                logger.info(
                    f"Admin '{request.user.username}' initiating custom domain creation for '{obj.domain_name}' (API: {obj.api_name})"
                )

                obj.create_custom_domain()
                messages.success(request, f"{obj.domain_name} custom domain created")

                logger.info(
                    f"Custom domain '{obj.domain_name}' created successfully for '{obj.api_name}' by '{request.user.username}'"
                )
            except ValueError as ve:
                logger.warning(
                    f"Validation error creating custom domain for '{obj.api_name}' by '{request.user.username}': {str(ve)}"
                )
                messages.error(request, f"{obj.api_name}: {str(ve)}")
            except Exception as e:
                # Security: Log errors without exposing sensitive details
                logger.error(
                    f"Failed to create custom domain for '{obj.api_name}' by '{request.user.username}': {str(e)}",
                    exc_info=True
                )
                messages.error(request, f"Failed to create custom domain for {obj.api_name}: {type(e).__name__}")


class ApiGatewayAdditionalRouteInline(TabularInline):
    autocomplete_fields = ["api_gateway"]
    model = ApiGatewayAdditionalRoute
    extra = 1

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_gateway")


@admin.register(WebSocketSession)
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


@admin.register(ApiGateway)
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


@admin.register(ApiGatewayAdditionalRoute)
class ApiGatewayAdditionalRouteAdmin(ModelAdmin):
    autocomplete_fields = ["api_gateway"]
    search_fields = ["name", "key"]
    list_display = ["name", "api_gateway", "route_key", "integration_url", "deployed"]
    list_filter = ["api_gateway"]
    date_hierarchy = "created_on"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_gateway")


@admin.register(WebSocketToken)
class WebSocketTokenAdmin(admin.ModelAdmin):
    list_display = ('token_preview', 'user', 'session_key', 'created_at', 'used')
    list_filter = ('used', 'created_at')
    search_fields = ('user__username', 'user__email', 'session_key')
    readonly_fields = ('token', 'user', 'session_key', 'created_at', 'used')

    def token_preview(self, obj):
        """Show only first 16 characters of token for security"""
        return f"{obj.token[:16]}..."

    token_preview.short_description = 'Token'

    def has_add_permission(self, request):
        # Tokens should only be created programmatically
        return False

    def has_change_permission(self, request, obj=None):
        # Tokens should not be modified
        return False


@admin.register(ConnectionRateLimit)
class ConnectionRateLimitAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'user', 'attempt_time', 'successful')
    list_filter = ('successful', 'attempt_time')
    search_fields = ('ip_address', 'user__username', 'user__email')
    readonly_fields = ('ip_address', 'user', 'attempt_time', 'successful')
    date_hierarchy = 'attempt_time'

    def has_add_permission(self, request):
        # Rate limits should only be created programmatically
        return False

    def has_change_permission(self, request, obj=None):
        # Rate limits should not be modified
        return False
