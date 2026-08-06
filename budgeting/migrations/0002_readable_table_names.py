from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="supply",
            table="budgeting_supply",
        ),
        migrations.AlterModelTable(
            name="servicecomposition",
            table="budgeting_service_composition",
        ),
        migrations.AlterModelTable(
            name="servicecompositionversion",
            table="budgeting_service_composition_version",
        ),
        migrations.AlterModelTable(
            name="servicecompositionitem",
            table="budgeting_service_composition_item",
        ),
        migrations.AlterModelTable(
            name="legacyimportrun",
            table="budgeting_legacy_import_run",
        ),
        migrations.AlterModelOptions(
            name="supply",
            options={
                "ordering": ("description", "id"),
                "verbose_name": "insumo",
                "verbose_name_plural": "insumos",
            },
        ),
        migrations.AlterModelOptions(
            name="servicecomposition",
            options={
                "ordering": ("name", "id"),
                "verbose_name": "composição de serviço",
                "verbose_name_plural": "composições de serviço",
            },
        ),
        migrations.AlterModelOptions(
            name="servicecompositionversion",
            options={
                "ordering": ("composition_id", "-number"),
                "verbose_name": "versão da composição de serviço",
                "verbose_name_plural": "versões das composições de serviço",
            },
        ),
        migrations.AlterModelOptions(
            name="servicecompositionitem",
            options={
                "ordering": ("position", "id"),
                "verbose_name": "item da composição de serviço",
                "verbose_name_plural": "itens das composições de serviço",
            },
        ),
        migrations.AlterModelOptions(
            name="legacyimportrun",
            options={
                "ordering": ("-started_at",),
                "verbose_name": "execução de importação legada",
                "verbose_name_plural": "execuções de importação legada",
            },
        ),
    ]
