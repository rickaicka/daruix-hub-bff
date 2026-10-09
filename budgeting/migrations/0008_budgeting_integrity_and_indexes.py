from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0007_remove_supply_code"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="materialgroup",
            options={
                "ordering": ("legacy_id", "nome", "id"),
                "verbose_name": "Grupo de material",
                "verbose_name_plural": "Grupos de materiais",
            },
        ),
        migrations.AlterModelOptions(
            name="unitmeasure",
            options={
                "ordering": ("legacy_id", "nome", "id"),
                "verbose_name": "Unidade de medida",
                "verbose_name_plural": "Unidades de medida",
            },
        ),
        migrations.AlterField(
            model_name="materialgroup",
            name="legacy_id",
            field=models.PositiveIntegerField(
                db_index=True,
                verbose_name="ID no legado",
            ),
        ),
        migrations.AlterField(
            model_name="unitmeasure",
            name="legacy_id",
            field=models.PositiveIntegerField(
                unique=True,
                verbose_name="ID no legado",
            ),
        ),
        migrations.AddConstraint(
            model_name="materialgroup",
            constraint=models.UniqueConstraint(
                fields=("legacy_id", "nome"),
                name="uq_material_group_legacy_name",
            ),
        ),
        migrations.AddIndex(
            model_name="supply",
            index=models.Index(
                fields=("is_active", "description"),
                name="supply_active_desc_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servicecomposition",
            index=models.Index(
                fields=("is_active", "name"),
                name="composition_active_name_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="servicecompositionitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        item_type="SUPPLY",
                        supply__isnull=False,
                        subcomposition__isnull=True,
                    )
                    | models.Q(
                        item_type="SUBCOMPOSITION",
                        supply__isnull=True,
                        subcomposition__isnull=False,
                    )
                    | models.Q(
                        item_type="FREE_TEXT",
                        supply__isnull=True,
                        subcomposition__isnull=True,
                    )
                ),
                name="ck_composition_item_reference",
            ),
        ),
        migrations.AddConstraint(
            model_name="servicecompositionitem",
            constraint=models.CheckConstraint(
                condition=models.Q(coefficient__gte=0),
                name="ck_composition_item_coefficient_gte_0",
            ),
        ),
        migrations.AddConstraint(
            model_name="servicecompositionitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(material_unit_price__gte=0)
                    & models.Q(labor_unit_price__gte=0)
                    & models.Q(equipment_unit_price__gte=0)
                ),
                name="ck_composition_item_prices_gte_0",
            ),
        ),
    ]
