from django.db import migrations, models


def delete_existing_tokens(apps, schema_editor):
    """Remove tokens that hold a raw session key.

    Tokens are single use and valid for about a minute, so nothing of value is lost.
    Rows written before this migration cannot be matched against the hashed value
    anyway, and they would otherwise keep live session keys in the database.
    """
    WebSocketToken = apps.get_model(
        "django_aws_api_gateway_websockets", "WebSocketToken"
    )
    WebSocketToken.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        (
            "django_aws_api_gateway_websockets",
            "0009_alter_connectionratelimit_table_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(delete_existing_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="websockettoken",
            name="session_key",
            field=models.CharField(db_index=True, max_length=64),
        ),
    ]
