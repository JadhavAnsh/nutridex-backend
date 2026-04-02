from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Authentication", "0009_user_bmi_user_conditions_user_height_user_weight"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="clerk_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
