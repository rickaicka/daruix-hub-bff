from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_remove_hubmenuitem_permission_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="hubmenuitem",
            name="descricao",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Descrição da página",
                help_text="Texto opcional exibido abaixo do título da funcionalidade no Hub Shell.",
            ),
        ),
    ]
