import logging

from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin, TabularInline
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from .models import (
    ApiGateway,
    ApiGatewayAdditionalRoute,
    ChannelPermission,
    ChannelPermissionRule,
    ConnectionRateLimit,
    WebSocketSession,
    WebSocketToken,
)
from .sync import ApiGatewaySyncError

logger = logging.getLogger(__name__)


@admin.action(description="Create API Gateway", permissions=["change"])
def create_api_gateway(modeladmin, request, queryset):
    """Creates the API Gateway record if one does not already exist"""
    for obj in queryset:
        if obj.needs_api_creation:
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

            except ValueError as ve:
                logger.warning(
                    f"Validation error creating API Gateway '{obj.api_name}' by '{request.user.username}': {str(ve)}"
                )
                messages.error(request, f"{obj.api_name}: {str(ve)}")
            except Exception as e:
                # Security: Log errors without exposing sensitive details to user
                logger.error(
                    f"Failed to create API Gateway '{obj.api_name}' (ID: {obj.pk}) by '{request.user.username}': {str(e)}",
                    exc_info=True,
                )
                messages.error(
                    request, f"Failed to create {obj.api_name}: {type(e).__name__}"
                )


@admin.action(description="Create Custom Domain", permissions=["change"])
def create_custom_domain(self, request, queryset):
    """Using the queryset, call the create_custom_domain method to create a custom domain"""
    for obj in queryset:
        if obj.needs_custom_domain:
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
                    exc_info=True,
                )
                messages.error(
                    request,
                    f"Failed to create custom domain for {obj.api_name}: {type(e).__name__}",
                )


def _run_sync(request, queryset, method_name: str, verb: str) -> None:
    """Run ``sync_to_aws`` or ``sync_from_aws`` on each gateway and report each result."""
    for obj in queryset:
        # Security: Audit log administrative actions
        logger.info(
            "Admin '%s' initiating sync %s AWS for '%s' (ID: %s)",
            request.user.username,
            verb,
            obj.api_name,
            obj.pk,
        )
        try:
            changes = getattr(obj, method_name)()
        except ValueError as error:
            messages.error(request, f"{obj.api_name}: {error}")
        except ApiGatewaySyncError as error:
            messages.error(
                request, f"{obj.api_name}: could not sync {verb} AWS ({error})"
            )
        else:
            if changes:
                messages.success(
                    request,
                    f"{obj.api_name}: synced {verb} AWS. " + "; ".join(changes),
                )
            else:
                messages.info(request, f"{obj.api_name}: already in sync with AWS")


@admin.action(description=_("Sync from AWS"), permissions=["change"])
def sync_from_aws(modeladmin, request, queryset):
    """Read the deployed API Gateways in AWS into the local records"""
    _run_sync(request, queryset, "sync_from_aws", "from")


@admin.action(description=_("Sync to AWS"), permissions=["change"])
def sync_to_aws(modeladmin, request, queryset):
    """Write the local records to the deployed API Gateways in AWS"""
    _run_sync(request, queryset, "sync_to_aws", "to")


class ApiGatewayAdditionalRouteInline(TabularInline):
    autocomplete_fields = ["api_gateway"]
    model = ApiGatewayAdditionalRoute
    extra = 1

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_gateway")


class SyncErrorMessageMixin:
    """Keep local changes when AWS rejects them, and tell the user instead of showing an error page."""

    def _report(self, request, error: ApiGatewaySyncError) -> None:
        messages.error(
            request,
            _(
                "AWS was not fully updated (%(error)s). Use the 'Sync to AWS' action on the "
                "API gateway to try again."
            )
            % {"error": error},
        )

    def save_model(self, request, obj, form, change):
        try:
            super().save_model(request, obj, form, change)
        except ApiGatewaySyncError as error:
            self._report(request, error)

    def delete_model(self, request, obj):
        try:
            super().delete_model(request, obj)
        except ApiGatewaySyncError as error:
            self._report(request, error)

    def save_formset(self, request, form, formset, change):
        """Save each additional route on its own, so one AWS failure does not skip the rest."""
        if formset.model is not ApiGatewayAdditionalRoute:
            return super().save_formset(request, form, formset, change)
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            self.delete_model(request, obj)
        for instance in instances:
            self.save_model(request, instance, form, change)
        formset.save_m2m()


@admin.register(WebSocketSession)
class WebSocketSessionAdmin(ModelAdmin):
    search_fields = ["connection_id", "channel_name"]
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

    def has_add_permission(self, request):
        # Sessions are created by the connect route. Adding or editing one here would
        # let staff attach a live connection to any user.
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApiGateway)
class ApiGatewayAdmin(SyncErrorMessageMixin, ModelAdmin):
    search_fields = ["domain_name", "api_name"]
    list_display = [
        "api_name",
        "domain_name",
        "default_channel_name",
        "api_id",
        "api_endpoint",
        "api_gateway_domain_name",
        "provisioning_status",
        "api_created",
        "deployment_id",
        "custom_domain_created",
        "created_on",
        "updated_on",
    ]
    list_filter = ["provisioning_status", "api_created", "custom_domain_created"]
    readonly_fields = ["last_error", "api_created", "deployment_id"]
    actions = [create_api_gateway, create_custom_domain, sync_from_aws, sync_to_aws]
    date_hierarchy = "created_on"
    inlines = [
        ApiGatewayAdditionalRouteInline,
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("additional_routes")


@admin.register(ApiGatewayAdditionalRoute)
class ApiGatewayAdditionalRouteAdmin(SyncErrorMessageMixin, ModelAdmin):
    autocomplete_fields = ["api_gateway"]
    search_fields = ["name", "route_key"]
    list_display = ["name", "api_gateway", "route_key", "integration_url", "deployed"]
    list_filter = ["api_gateway"]
    date_hierarchy = "created_on"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_gateway")


@admin.register(WebSocketToken)
class WebSocketTokenAdmin(admin.ModelAdmin):
    list_display = ("token_preview", "user", "created_at", "used")
    list_filter = ("used", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("token", "user", "created_at", "used")
    # The stored session key hash is not shown: it is derived from a login credential
    exclude = ("session_key",)

    def token_preview(self, obj):
        """Show only first 16 characters of token for security"""
        return f"{obj.token[:16]}..."

    token_preview.short_description = "Token"

    def has_add_permission(self, request):
        # Tokens should only be created programmatically
        return False

    def has_change_permission(self, request, obj=None):
        # Tokens should not be modified
        return False


@admin.register(ConnectionRateLimit)
class ConnectionRateLimitAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "user", "attempt_time", "successful")
    list_filter = ("successful", "attempt_time")
    search_fields = ("ip_address", "user__username", "user__email")
    readonly_fields = ("ip_address", "user", "attempt_time", "successful")
    date_hierarchy = "attempt_time"

    def has_add_permission(self, request):
        # Rate limits should only be created programmatically
        return False

    def has_change_permission(self, request, obj=None):
        # Rate limits should not be modified
        return False


class ChannelPermissionRuleInline(TabularInline):
    """A rule is one set of permissions the user must all have. Add rules for alternatives."""

    model = ChannelPermissionRule
    extra = 0
    filter_horizontal = ["permissions"]


@admin.register(ChannelPermission)
class ChannelPermissionAdmin(ModelAdmin):
    list_display = ["channel_name", "access", "rules_summary", "updated_on"]
    list_filter = ["access"]
    search_fields = ["channel_name", "description"]
    inlines = [ChannelPermissionRuleInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                Prefetch(
                    "rules",
                    queryset=ChannelPermissionRule.objects.prefetch_related(
                        "permissions__content_type"
                    ),
                )
            )
        )

    @admin.display(description=_("Rules"))
    def rules_summary(self, obj) -> str:
        """Show the rules as ``A AND B  OR  C`` (only used by 'Requires Django permissions')"""
        if obj.access != ChannelPermission.Access.PERMISSIONS:
            return ""
        return "  OR  ".join(f"({rule})" for rule in obj.rules.all())
