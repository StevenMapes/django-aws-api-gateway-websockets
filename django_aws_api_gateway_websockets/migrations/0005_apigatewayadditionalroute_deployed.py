# Generated by Django 3.2.11 on 2022-12-08 13:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_aws_api_gateway_websockets", "0004_auto_20221208_1227"),
    ]

    operations = [
        migrations.AddField(
            model_name="apigatewayadditionalroute",
            name="deployed",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
