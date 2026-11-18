from budgeting.models import BudgetSheetStageItem
from material_requisitions.models import MaterialRequisitionItem


def composition_paths(quotation):
    """Recover display ancestors from the approved RM and the frozen budget sheet."""
    items = MaterialRequisitionItem.objects.filter(
        pk__in=[item["id"] for item in quotation.items],
        section__revision_id=quotation.approved_revision_id,
    ).exclude(source_path="").values_list(
        "pk", "section_id", "section__source_stage_id",
        "section__source_composition_id", "source_path",
    )
    origins = {}
    for item_id, section_id, stage_id, legacy_source, path in items:
        parts = path.split(".")
        if parts[0] == "po":
            if len(parts) < 3 or not parts[1].isdigit():
                continue
            source_id, parts = int(parts[1]), parts[2:]
        else:
            source_id = legacy_source
        if source_id and all(part.isdigit() for part in parts):
            origins[item_id] = (section_id, stage_id, source_id, parts)

    if not origins:
        return {}

    sources = BudgetSheetStageItem.objects.filter(
        pk__in={origin[2] for origin in origins.values()},
        item_type="SERVICE_COMPOSITION",
    ).only("budget_sheet_stage_id", "description_snapshot", "composition_snapshot")
    compositions = {
        source.pk: (source, {
            str(row.get("source_path")): row["description_snapshot"]
            for row in source.composition_snapshot.get("items", [])
            if row.get("item_type") == "SUBCOMPOSITION" and row.get("description_snapshot")
        })
        for source in sources
    }
    result = {}
    for item_id, (section_id, stage_id, source_id, parts) in origins.items():
        entry = compositions.get(source_id)
        if entry is None or entry[0].budget_sheet_stage_id != stage_id:
            continue
        source, subcompositions = entry
        root = f"{section_id}:{source_id}"
        path = [{"key": root, "label": source.description_snapshot or "Serviço composto"}]
        for index in range(1, len(parts)):
            prefix = ".".join(parts[:index])
            if label := subcompositions.get(prefix):
                path.append({"key": f"{root}:{prefix}", "label": label})
        result[item_id] = path
    return result
