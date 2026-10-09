from django.db import migrations, models


def preserve_supply_base(apps, schema_editor):
    Item = apps.get_model("budgeting", "BudgetSheetStageItem")
    # Até 0017 insumos nunca recebiam BDI. Preservar seu valor atual como
    # base, sem presumir qual parte já era margem no cadastro do usuário.
    Item.objects.using(schema_editor.connection.alias).filter(item_type="SUPPLY").update(
        unit_cost=models.F("unit_price"),
    )


def disable_supply_bdi(apps, schema_editor):
    Item = apps.get_model("budgeting", "BudgetSheetStageItem")
    Item.objects.using(schema_editor.connection.alias).filter(item_type="SUPPLY").update(apply_bdi=False)


class Migration(migrations.Migration):
    dependencies = [("budgeting", "0017_budget_sheet_cost_configuration")]
    operations = [
        migrations.RemoveConstraint("budgetsheetstageitem", "ck_budget_stage_item_bdi_only_composition"),
        migrations.RunPython(preserve_supply_base, disable_supply_bdi),
        migrations.AddConstraint(
            model_name="budgetsheetstageitem",
            constraint=models.CheckConstraint(
                condition=models.Q(item_type__in=["SERVICE_COMPOSITION", "SUPPLY"]) | models.Q(apply_bdi=False),
                name="ck_budget_stage_item_bdi_priced_item",
            ),
        ),
    ]
