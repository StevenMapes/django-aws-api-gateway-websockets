# Generated by Django 3.2.11 on 2022-12-08 12:27

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_aws_api_gateway_websockets", "0003_auto_20220706_1018"),
    ]

    operations = [
        migrations.AddField(
            model_name="apigateway",
            name="deployment_id",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=32
            ),
        ),
        migrations.CreateModel(
            name="ApiGatewayAdditionalRoute",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Descriptive name for the route", max_length=63
                    ),
                ),
                ("route_key", models.CharField(max_length=64, unique=True)),
                ("integration_url", models.URLField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("updated_on", models.DateTimeField(auto_now=True)),
                (
                    "api_gateway",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="additional_routes",
                        to="django_aws_api_gateway_websockets.apigateway",
                    ),
                ),
            ],
        ),
    ]