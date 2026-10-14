from unittest.mock import MagicMock, patch

from botocore import exceptions
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, SimpleTestCase, TestCase

from django_aws_api_gateway_websockets import admin, models
from django_aws_api_gateway_websockets.sync import ApiGatewaySyncError


class CreateApiGatewaySimpleTestCase(SimpleTestCase):
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_empty_queryset(self, mocked_messages):
        """Empty queryset means nothing should run"""
        queryset = []

        admin.create_api_gateway(None, None, queryset)

        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_not_yet_created(self, mocked_messages):
        """When the record does not yet have an API that has been created, it should call create_gateway"""
        request = MagicMock()
        instance = MagicMock(
            api_created=False,
            custom_domain_created=False,
            needs_api_creation=True,
            needs_custom_domain=False,
            api_name="Test API",
        )
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        instance.create_gateway.assert_called_with()
        mocked_messages.success.assert_called_with(
            request, f"{instance.api_name} created"
        )
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    @patch("django_aws_api_gateway_websockets.admin.logger")
    def test_api_already_created(self, mocked_logger, mocked_messages):
        """When the api_created boolean is True the record should be skipped"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            needs_api_creation=False,
            needs_custom_domain=True,
            api_name="Test API",
        )
        instance.create_gateway.return_value = False
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        self.assertEqual(0, instance.create_gateway.call_count)
        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_client_error_raised(self, mocked_messages):
        """When a ClientError occurs an error message should be added"""
        request = MagicMock()
        instance = MagicMock(
            api_created=False,
            custom_domain_created=False,
            needs_api_creation=True,
            needs_custom_domain=False,
            api_name="Test API",
        )
        instance.create_gateway.side_effect = exceptions.ClientError(
            {"Error": {"Code": "A123", "Message": "Some error"}}, "apigateway"
        )
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        instance.create_gateway.assert_called_with()
        self.assertEqual(0, mocked_messages.success.call_count)
        mocked_messages.error.assert_called_with(
            request, f"Failed to create {instance.api_name}: ClientError"
        )


class CreatCustomDomainSimpleTestCase(SimpleTestCase):
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_empty_queryset(self, mocked_messages):
        """Empty queryset means nothing should run"""
        queryset = []

        admin.create_custom_domain(None, None, queryset)

        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_created_but_custom_domain_not_created(self, mocked_messages):
        """When the record does not yet have an API that has been created, it should call create_gateway"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            needs_api_creation=False,
            needs_custom_domain=True,
            api_name="Test API",
            api_gateway_domain_name="ws.example.com",
        )
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        instance.create_custom_domain.assert_called_with()
        mocked_messages.success.assert_called_with(
            request, f"{instance.domain_name} custom domain created"
        )
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_api_and_custom_domain_both_created(self, mocked_messages):
        """When the api_created boolean is True the record should be skipped"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=True,
            needs_api_creation=False,
            needs_custom_domain=False,
            api_name="Test API",
            api_gateway_domain_name="ws.example.com",
        )
        instance.create_custom_domain.return_value = True
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        self.assertEqual(0, instance.create_custom_domain.call_count)
        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_client_error_raised(self, mocked_messages):
        """When a ClientError occurs an error message should be added"""
        request = MagicMock()
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            needs_api_creation=False,
            needs_custom_domain=True,
            api_name="Test API",
            api_gateway_domain_name="ws.example.com",
        )
        instance.create_custom_domain.side_effect = exceptions.ClientError(
            {"Error": {"Code": "A123", "Message": "Some error"}}, "apigateway"
        )
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        instance.create_custom_domain.assert_called_with()
        self.assertEqual(0, mocked_messages.success.call_count)
        mocked_messages.error.assert_called_with(
            request,
            f"Failed to create custom domain for {instance.api_name}: ClientError",
        )


class AdminTestCase(TestCase):
    """Tests that require the database"""

    def setUp(self) -> None:
        self.user, _ = User.objects.get_or_create(
            username="test", is_staff=True, is_superuser=True
        )

    def test_WebSocketSessionAdmin_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.WebSocketSessionAdmin(
            model=models.WebSocketSession, admin_site=AdminSite()
        )
        request = RequestFactory().get("/view-path")
        site.get_queryset(request)

    def test_ApiGatewayAdmin_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.ApiGatewayAdmin(model=models.ApiGateway, admin_site=AdminSite())
        request = RequestFactory().get("/view-path")
        site.get_queryset(request)

    def test_ApiGatewayAdditionalRouteAdmin_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.ApiGatewayAdditionalRouteAdmin(
            model=models.ApiGatewayAdditionalRoute, admin_site=AdminSite()
        )
        request = RequestFactory().get("/view-path")
        site.get_queryset(request)

    def test_ApiGatewayAdditionalRouteInline_queryset(self):
        """Ensure the overloaded queryset method is working"""
        site = admin.ApiGatewayAdditionalRouteInline(
            parent_model=models.ApiGatewayAdditionalRoute, admin_site=AdminSite()
        )
        request = RequestFactory().get("/view-path")
        request.user = self.user
        request.session = {}
        site.get_queryset(request)


class CreateApiGatewayAdditionalSimpleTestCase(SimpleTestCase):
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_create_gateway_returning_false_adds_info_message(self, mocked_messages):
        request = MagicMock()
        request.user.username = "admin-user"
        instance = MagicMock(
            api_created=False,
            custom_domain_created=False,
            needs_api_creation=True,
            needs_custom_domain=False,
            api_name="Test API",
            pk=1,
        )
        instance.create_gateway.return_value = False
        queryset = [instance]

        admin.create_api_gateway(None, request, queryset)

        instance.create_gateway.assert_called_with()
        mocked_messages.info.assert_called_with(
            request,
            f"{instance.api_name} already created",
        )
        self.assertEqual(0, mocked_messages.success.call_count)
        self.assertEqual(0, mocked_messages.error.call_count)


class CreateCustomDomainAdditionalSimpleTestCase(SimpleTestCase):
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_value_error_adds_error_message(self, mocked_messages):
        request = MagicMock()
        request.user.username = "admin-user"
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            needs_api_creation=False,
            needs_custom_domain=True,
            api_name="Test API",
            domain_name="ws.example.com",
        )
        instance.create_custom_domain.side_effect = ValueError("Certificate required")
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        instance.create_custom_domain.assert_called_with()
        mocked_messages.error.assert_called_with(
            request,
            "Test API: Certificate required",
        )

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_generic_exception_adds_safe_error_message(self, mocked_messages):
        request = MagicMock()
        request.user.username = "admin-user"
        instance = MagicMock(
            api_created=True,
            custom_domain_created=False,
            needs_api_creation=False,
            needs_custom_domain=True,
            api_name="Test API",
            domain_name="ws.example.com",
        )
        instance.create_custom_domain.side_effect = RuntimeError("Sensitive details")
        queryset = [instance]

        admin.create_custom_domain(None, request, queryset)

        instance.create_custom_domain.assert_called_with()
        mocked_messages.error.assert_called_with(
            request,
            "Failed to create custom domain for Test API: RuntimeError",
        )


class WebSocketTokenAdminSimpleTestCase(SimpleTestCase):
    def test_token_preview_masks_token(self):
        admin_instance = admin.WebSocketTokenAdmin(
            models.WebSocketToken,
            AdminSite(),
        )
        obj = MagicMock(token="a" * 64)

        self.assertEqual("aaaaaaaaaaaaaaaa...", admin_instance.token_preview(obj))

    def test_has_add_permission_returns_false(self):
        admin_instance = admin.WebSocketTokenAdmin(
            models.WebSocketToken,
            AdminSite(),
        )

        self.assertFalse(admin_instance.has_add_permission(MagicMock()))

    def test_has_change_permission_returns_false(self):
        admin_instance = admin.WebSocketTokenAdmin(
            models.WebSocketToken,
            AdminSite(),
        )

        self.assertFalse(admin_instance.has_change_permission(MagicMock()))


class ConnectionRateLimitAdminSimpleTestCase(SimpleTestCase):
    def test_has_add_permission_returns_false(self):
        admin_instance = admin.ConnectionRateLimitAdmin(
            models.ConnectionRateLimit,
            AdminSite(),
        )

        self.assertFalse(admin_instance.has_add_permission(MagicMock()))

    def test_has_change_permission_returns_false(self):
        admin_instance = admin.ConnectionRateLimitAdmin(
            models.ConnectionRateLimit,
            AdminSite(),
        )

        self.assertFalse(admin_instance.has_change_permission(MagicMock()))


class WebSocketAdminSecurityTestCase(TestCase):
    """The library's admin pages must not hand out credentials or edit identity."""

    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="root", password="pw")
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.user

    def _admin(self, admin_class, model):
        return admin_class(model=model, admin_site=AdminSite())

    def test_token_admin_never_exposes_the_session_key(self):
        token_admin = self._admin(admin.WebSocketTokenAdmin, models.WebSocketToken)

        self.assertNotIn("session_key", token_admin.list_display)
        self.assertNotIn("session_key", token_admin.search_fields)
        self.assertNotIn("session_key", token_admin.get_fields(self.request))
        self.assertNotIn("session_key", token_admin.get_readonly_fields(self.request))

    def test_session_admin_is_read_only(self):
        session_admin = self._admin(
            admin.WebSocketSessionAdmin, models.WebSocketSession
        )
        session = models.WebSocketSession.objects.create(
            connection_id="RO-1", user=self.user
        )

        self.assertFalse(session_admin.has_add_permission(self.request))
        self.assertFalse(session_admin.has_change_permission(self.request))
        self.assertFalse(session_admin.has_change_permission(self.request, session))
        self.assertTrue(session_admin.has_view_permission(self.request, session))
        self.assertTrue(session_admin.has_delete_permission(self.request, session))

    def test_session_admin_does_not_offer_the_user_as_an_editable_field(self):
        session_admin = self._admin(
            admin.WebSocketSessionAdmin, models.WebSocketSession
        )

        self.assertNotIn("user", session_admin.autocomplete_fields)

    def test_additional_route_admin_search_uses_real_fields(self):
        """A search on the changelist must not raise FieldError."""
        gateway = models.ApiGateway.objects.create(
            api_name="Search Gateway",
            target_base_endpoint="https://example.com/",
        )
        route = models.ApiGatewayAdditionalRoute.objects.create(
            api_gateway=gateway,
            name="Reports",
            route_key="report-route",
            integration_url="https://example.com/report",
        )
        route_admin = self._admin(
            admin.ApiGatewayAdditionalRouteAdmin, models.ApiGatewayAdditionalRoute
        )

        queryset, _ = route_admin.get_search_results(
            self.request, models.ApiGatewayAdditionalRoute.objects.all(), "report-route"
        )

        self.assertEqual([route], list(queryset))

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_create_api_gateway_action_reports_success_when_it_creates(
        self, mocked_messages, mocked_get_boto3_client
    ):
        """Not mocking create_gateway: a real creation must say 'created'."""
        client = mocked_get_boto3_client.return_value
        client.create_api.return_value = {"ApiId": "A1", "ApiEndpoint": "wss://x"}
        client.create_integration.return_value = {"IntegrationId": "i1"}
        client.create_deployment.return_value = {"DeploymentId": "d1"}
        gateway = models.ApiGateway.objects.create(
            api_name="Action Gateway",
            target_base_endpoint="https://example.com/ws/",
        )

        admin.create_api_gateway(
            None, self.request, models.ApiGateway.objects.filter(pk=gateway.pk)
        )

        mocked_messages.success.assert_called_once_with(
            self.request, "Action Gateway created"
        )
        mocked_messages.info.assert_not_called()
        mocked_messages.error.assert_not_called()

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_create_api_gateway_action_explains_a_missing_target_endpoint(
        self, mocked_messages, mocked_get_boto3_client
    ):
        gateway = models.ApiGateway.objects.create(
            api_name="No Target Gateway", target_base_endpoint=None
        )

        admin.create_api_gateway(
            None, self.request, models.ApiGateway.objects.filter(pk=gateway.pk)
        )

        mocked_get_boto3_client.assert_not_called()
        mocked_messages.error.assert_called_once()
        self.assertIn("target_base_endpoint", mocked_messages.error.call_args.args[1])


class ChannelPermissionAdminTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="cp-admin", password="pw")
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.user

    def test_channel_permission_is_registered_with_the_rules_inline(self):
        from django.contrib import admin as django_admin

        model_admin = django_admin.site._registry[models.ChannelPermission]

        self.assertIsInstance(model_admin, admin.ChannelPermissionAdmin)
        self.assertIn(admin.ChannelPermissionRuleInline, model_admin.inlines)

    def test_rules_inline_uses_a_permission_picker(self):
        inline = admin.ChannelPermissionRuleInline(
            models.ChannelPermission, AdminSite()
        )

        self.assertIn("permissions", inline.filter_horizontal)
        self.assertEqual(models.ChannelPermissionRule, inline.model)

    def test_changelist_can_be_searched_and_filtered(self):
        model_admin = admin.ChannelPermissionAdmin(
            models.ChannelPermission, AdminSite()
        )
        models.ChannelPermission.objects.create(channel_name="reports")

        queryset, _ = model_admin.get_search_results(
            self.request, models.ChannelPermission.objects.all(), "report"
        )

        self.assertEqual(1, queryset.count())
        self.assertIn("access", model_admin.list_filter)

    def test_rule_summary_lists_the_rules_in_the_changelist(self):
        model_admin = admin.ChannelPermissionAdmin(
            models.ChannelPermission, AdminSite()
        )
        channel = models.ChannelPermission.objects.create(
            channel_name="reports", access=models.ChannelPermission.Access.PERMISSIONS
        )
        rule = models.ChannelPermissionRule.objects.create(channel_permission=channel)
        rule.permissions.set([Permission.objects.get(codename="view_user")])

        queryset = model_admin.get_queryset(self.request)
        summary = model_admin.rules_summary(queryset.get(pk=channel.pk))

        self.assertIn("view_user", summary)


class ApiGatewayActionPermissionsTestCase(TestCase):
    """The actions that create AWS resources need the change permission, not just view."""

    ACTIONS = {"create_api_gateway", "create_custom_domain"}

    def setUp(self) -> None:
        self.model_admin = admin.ApiGatewayAdmin(models.ApiGateway, AdminSite())

    def _staff(self, *codenames, **kwargs):
        user = User.objects.create_user(
            username=f"staff{User.objects.count()}",
            password="pw",
            is_staff=True,
            **kwargs,
        )
        user.user_permissions.set(
            Permission.objects.filter(
                codename__in=codenames,
                content_type__app_label="django_aws_api_gateway_websockets",
            )
        )
        request = RequestFactory().get("/admin/")
        request.user = User.objects.get(pk=user.pk)  # drop the cached permissions
        return request

    def _action_names(self, request):
        return set(self.model_admin.get_actions(request))

    def test_view_only_staff_cannot_see_the_aws_actions(self):
        request = self._staff("view_apigateway")

        self.assertTrue(self.model_admin.has_view_permission(request))
        self.assertFalse(self._action_names(request) & self.ACTIONS)

    def test_staff_with_change_permission_can_use_the_aws_actions(self):
        request = self._staff("view_apigateway", "change_apigateway")

        self.assertGreaterEqual(self._action_names(request), self.ACTIONS)

    def test_superuser_can_use_the_aws_actions(self):
        request = self._staff(is_superuser=True)

        self.assertGreaterEqual(self._action_names(request), self.ACTIONS)

    def test_other_permissions_do_not_grant_the_aws_actions(self):
        request = self._staff(
            "view_apigateway", "change_websocketsession", "add_apigateway"
        )

        self.assertFalse(self._action_names(request) & self.ACTIONS)

    def test_the_actions_declare_the_permission_they_need(self):
        for action in (admin.create_api_gateway, admin.create_custom_domain):
            with self.subTest(action=action.__name__):
                self.assertEqual(["change"], list(action.allowed_permissions))


class ApiGatewayProvisioningAdminTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="prov", password="pw")
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.user
        self.model_admin = admin.ApiGatewayAdmin(models.ApiGateway, AdminSite())

    def test_the_changelist_shows_and_filters_by_provisioning_status(self):
        self.assertIn("provisioning_status", self.model_admin.list_display)
        self.assertIn("provisioning_status", self.model_admin.list_filter)

    def test_last_error_is_shown_but_not_editable(self):
        self.assertIn("last_error", self.model_admin.get_readonly_fields(self.request))
        self.assertIn("last_error", self.model_admin.get_fields(self.request))

    def test_provisioning_status_can_be_corrected_by_hand(self):
        """Lets an administrator mark a half-built gateway so it can be resumed."""
        self.assertNotIn(
            "provisioning_status", self.model_admin.get_readonly_fields(self.request)
        )
        self.assertIn("provisioning_status", self.model_admin.get_fields(self.request))

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_the_action_resumes_a_half_built_gateway(
        self, mocked_messages, mocked_get_boto3_client
    ):
        client = mocked_get_boto3_client.return_value
        client.get_routes.return_value = {"Items": []}
        client.create_integration.return_value = {"IntegrationId": "i1"}
        client.create_deployment.return_value = {"DeploymentId": "d1"}
        gateway = models.ApiGateway.objects.create(
            api_name="Half Built",
            target_base_endpoint="https://example.com/ws/",
            api_id="A1",
            api_created=True,
            provisioning_status=models.ApiGateway.ProvisioningStatus.API_CREATED,
        )

        admin.create_api_gateway(
            None, self.request, models.ApiGateway.objects.filter(pk=gateway.pk)
        )

        mocked_messages.success.assert_called_once_with(
            self.request, "Half Built created"
        )
        client.create_api.assert_not_called()
        gateway.refresh_from_db()
        self.assertEqual("deployed", gateway.provisioning_status)


class SyncActionsTestCase(SimpleTestCase):
    def setUp(self):
        self.request = MagicMock()
        self.request.user.username = "admin"

    def gateway(self, **kwargs):
        gateway = MagicMock()
        gateway.api_name = "gw"
        for name, value in kwargs.items():
            setattr(gateway, name, value)
        return gateway

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_sync_to_aws_reports_the_changes(self, mocked_messages):
        gateway = self.gateway()
        gateway.sync_to_aws.return_value = [
            "Updated the API Name",
            "Deployed the stage",
        ]

        admin.sync_to_aws(None, self.request, [gateway])

        mocked_messages.success.assert_called_once_with(
            self.request,
            "gw: synced to AWS. Updated the API Name; Deployed the stage",
        )

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_sync_from_aws_reports_the_changes(self, mocked_messages):
        gateway = self.gateway()
        gateway.sync_from_aws.return_value = ["Updated api_name"]

        admin.sync_from_aws(None, self.request, [gateway])

        mocked_messages.success.assert_called_once_with(
            self.request, "gw: synced from AWS. Updated api_name"
        )
        gateway.sync_to_aws.assert_not_called()

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_no_changes_is_reported_as_in_sync(self, mocked_messages):
        gateway = self.gateway()
        gateway.sync_to_aws.return_value = []

        admin.sync_to_aws(None, self.request, [gateway])

        mocked_messages.info.assert_called_once_with(
            self.request, "gw: already in sync with AWS"
        )

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_an_undeployed_gateway_is_reported_as_an_error(self, mocked_messages):
        gateway = self.gateway()
        gateway.sync_to_aws.side_effect = ValueError("must be deployed")

        admin.sync_to_aws(None, self.request, [gateway])

        mocked_messages.error.assert_called_once_with(
            self.request, "gw: must be deployed"
        )

    @patch("django_aws_api_gateway_websockets.admin.messages")
    def test_an_aws_failure_is_reported_without_stopping_the_other_gateways(
        self, mocked_messages
    ):
        failing, working = self.gateway(), self.gateway(api_name="ok")
        failing.sync_from_aws.side_effect = ApiGatewaySyncError("ClientError: Denied")
        working.sync_from_aws.return_value = []

        admin.sync_from_aws(None, self.request, [failing, working])

        mocked_messages.error.assert_called_once_with(
            self.request, "gw: could not sync from AWS (ClientError: Denied)"
        )
        mocked_messages.info.assert_called_once_with(
            self.request, "ok: already in sync with AWS"
        )

    def test_the_actions_need_the_change_permission_and_are_listed(self):
        for action in (admin.sync_to_aws, admin.sync_from_aws):
            self.assertEqual(["change"], list(action.allowed_permissions))
        self.assertEqual("Sync to AWS", str(admin.sync_to_aws.short_description))
        self.assertEqual("Sync from AWS", str(admin.sync_from_aws.short_description))
        self.assertIn(admin.sync_to_aws, admin.ApiGatewayAdmin.actions)
        self.assertIn(admin.sync_from_aws, admin.ApiGatewayAdmin.actions)


class ApiGatewayDeploymentFieldsAdminTestCase(TestCase):
    def setUp(self):
        self.model_admin = admin.ApiGatewayAdmin(models.ApiGateway, AdminSite())

    def test_deployment_id_and_api_created_are_shown_and_read_only(self):
        self.assertIn("deployment_id", self.model_admin.list_display)
        self.assertIn("api_created", self.model_admin.list_display)
        self.assertIn("deployment_id", self.model_admin.readonly_fields)
        self.assertIn("api_created", self.model_admin.readonly_fields)

    def test_the_change_form_includes_both_fields(self):
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("root", "r@example.com", "pw")
        fields = self.model_admin.get_fields(request)
        self.assertIn("deployment_id", fields)
        self.assertIn("api_created", fields)

    def test_an_aws_failure_on_save_is_reported_and_the_change_kept(self):
        request = MagicMock()
        obj = MagicMock()
        obj.save.side_effect = ApiGatewaySyncError("ClientError: Denied")
        with patch("django_aws_api_gateway_websockets.admin.messages") as messages:
            self.model_admin.save_model(request, obj, MagicMock(), True)
        messages.error.assert_called_once()
        self.assertIn("ClientError: Denied", str(messages.error.call_args.args[1]))

    def test_inline_routes_are_saved_one_by_one_when_aws_fails(self):
        request = MagicMock()
        first, second = MagicMock(), MagicMock()
        first.save.side_effect = ApiGatewaySyncError("ClientError: Denied")
        formset = MagicMock()
        formset.model = models.ApiGatewayAdditionalRoute
        formset.save.return_value = [first, second]
        formset.deleted_objects = []
        with patch("django_aws_api_gateway_websockets.admin.messages") as messages:
            self.model_admin.save_formset(request, MagicMock(), formset, True)
        second.save.assert_called_once()
        messages.error.assert_called_once()
        formset.save_m2m.assert_called_once()

    def test_an_aws_failure_on_inline_delete_is_reported(self):
        request = MagicMock()
        formset = MagicMock()
        formset.model = models.ApiGatewayAdditionalRoute
        formset.save.return_value = []
        stuck = MagicMock()
        stuck.delete.side_effect = ApiGatewaySyncError("ClientError: Denied")
        formset.deleted_objects = [stuck]
        with patch("django_aws_api_gateway_websockets.admin.messages") as messages:
            self.model_admin.save_formset(request, MagicMock(), formset, True)
        messages.error.assert_called_once()
