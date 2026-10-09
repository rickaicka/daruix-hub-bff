from __future__ import annotations

from decimal import Decimal
from copy import deepcopy
from io import BytesIO
from typing import Any, Literal

from django.core.exceptions import ValidationError

from budgeting.choices import BudgetSheetItemType, BudgetSheetStatus
from budgeting.models import BudgetSheet, BudgetSheetStage

ExportAudience = Literal["CLIENT", "DARUIX"]
PdfDocument = Literal["PLANILHA", "BDI", "DI"]


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _require_finalized(sheet: BudgetSheet) -> None:
    if sheet.status != BudgetSheetStatus.FINALIZED:
        raise ValidationError(
            "A exportação oficial só é permitida para revisões finalizadas. "
            "Finalize o orçamento antes de exportar."
        )


def _sheet_with_tree(sheet_id: int) -> BudgetSheet:
    return (
        BudgetSheet.objects
        .select_related("proposal", "party", "department")
        .prefetch_related("stages__stage", "stages__items")
        .get(pk=sheet_id)
    )


def build_export_preview(sheet_id: int, audience: ExportAudience) -> dict[str, Any]:
    if audience not in ("CLIENT", "DARUIX"):
        raise ValidationError({"audience": "Use CLIENT ou DARUIX."})

    sheet = _sheet_with_tree(sheet_id)
    _require_finalized(sheet)
    nodes: list[dict[str, Any]] = []

    for stage in sorted(sheet.stages.all(), key=lambda row: (row.order, row.id)):
        stage_node: dict[str, Any] = {
            "number": str(stage.order),
            "kind": "STAGE",
            "description": stage.name_snapshot,
            "children": [],
        }

        for item in sorted(stage.items.all(), key=lambda row: (row.order, row.id)):
            item_number = f"{stage.order}.{item.order}"
            item_node: dict[str, Any] = {
                "number": item_number,
                "kind": "COMPOSITION" if item.item_type == BudgetSheetItemType.SERVICE_COMPOSITION else "ITEM",
                "description": item.description_snapshot,
                "unit": item.unit_snapshot,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "total": str(item.subtotal),
                "children": [],
            }

            if audience == "DARUIX" and item.item_type == BudgetSheetItemType.SERVICE_COMPOSITION:
                snapshot = item.composition_snapshot or {}
                for leaf_index, component in enumerate(snapshot.get("items") or [], start=1):
                    if component.get("display_only"):
                        continue

                    if component.get("enabled", True) is False:
                        continue
                    coefficient = _decimal(component.get("coefficient"))
                    quantity = _decimal(item.quantity) * coefficient
                    source_path = str(component.get("source_path") or leaf_index)
                    item_node["children"].append(
                        {
                            "number": f"{item_number}.{source_path}",
                            "kind": "SUPPLY",
                            "description": component.get("description_snapshot") or "",
                            "unit": component.get("unit_snapshot") or "",
                            "quantity": str(quantity),
                            "material_unit_cost": component.get("material_unit_price") or "0",
                            "labor_unit_cost": component.get("labor_unit_price") or "0",
                            "equipment_unit_cost": component.get("equipment_unit_price") or "0",
                        }
                    )

            # Segurança: em CLIENT nenhum campo de custo interno ou quebra da
            # composição é sequer colocado no payload. Não é apenas escondido
            # no front-end.
            stage_node["children"].append(item_node)

        nodes.append(stage_node)

    return {
        "audience": audience,
        "budget_sheet_id": sheet.pk,
        "number": sheet.number,
        "revision": sheet.revision,
        "proposal_code": getattr(sheet.proposal, "code", None),
        "party_name": str(sheet.party) if sheet.party_id else None,
        "total_amount": str(sheet.total_amount),
        "nodes": nodes,
    }


def _export_data(sheet, audience, *, include_pdf_reports=False):
    """CLIENT permite valores finais, nunca custos abertos, fórmulas ou snapshots."""
    internal = audience == "DARUIX"
    proposal = sheet.proposal if sheet.proposal_id else None
    work = getattr(proposal, "work", None)
    from .budget_export_branding import work_location
    data = {
        "audience": audience, "number": sheet.number, "revision": sheet.revision,
        "proposal_code": getattr(proposal, "code", "") or "",
        "party_name": str(sheet.party) if sheet.party_id else "",
        "work_name": getattr(work, "name", "") or getattr(proposal, "work_name", "") or "",
        "work_location": work_location(proposal, work),
        "date": sheet.reference_date.strftime("%d/%m/%Y"),
        "total": str(sheet.total_amount), "stages": [],
    }
    for stage in sorted(sheet.stages.all(), key=lambda x: (x.order, x.id)):
        target = {"number": str(stage.order), "name": stage.name_snapshot,
                  "total": str(stage.subtotal), "items": []}
        for item in sorted(stage.items.all(), key=lambda x: (x.order, x.id)):
            row = {"number": f"{stage.order}.{item.order}", "description": item.description_snapshot,
                   "unit": item.unit_snapshot, "quantity": str(item.quantity),
                   "unit_price": str(item.unit_price), "total": str(item.subtotal)}
            if internal:
                free = item.item_type == BudgetSheetItemType.FREE_TEXT
                row["cost"] = {
                    "material": str(item.unit_price if free else item.material_unit_cost),
                    "labor": str(0 if free else item.labor_unit_cost),
                    "equipment": str(0 if free else item.equipment_unit_cost),
                    "unit_cost": str(item.unit_price if free else item.unit_cost),
                    "apply_bdi": bool(item.apply_bdi) and not free,
                    "discount": str(getattr(item, "unit_discount", 0) or 0),
                    "components": (item.composition_snapshot or {}).get("items", []),
                }
            target["items"].append(row)
        data["stages"].append(target)
    if internal or include_pdf_reports:
        from .budget_costs import get_budget_cost_configuration, BDI_NON_TAX_KEYS, BDI_TAX_KEYS
        if internal:
            data["bdi_non_tax_keys"] = BDI_NON_TAX_KEYS
            data["bdi_tax_keys"] = BDI_TAX_KEYS
        memory = get_budget_cost_configuration(sheet)
        data["di"] = memory["di"]
        data["bdi"] = memory["bdi"]
        if not sheet.bdi_configuration:
            # A memória vazia tem resumo zerado no endpoint. Para o relatório,
            # demonstre os custos da revisão sem persistir nem aplicar BDI.
            from .budget_costs import _calculate_bdi, budget_sheet_direct_cost_breakdown
            data["bdi"] = _calculate_bdi(
                deepcopy(memory["bdi"]), direct_cost=budget_sheet_direct_cost_breakdown(sheet),
                di_config=memory["di"],
            )
        if not data["bdi"].get("configured"):
            data["bdi"]["calculated_factor"] = "1.000000000000"
            data["bdi"]["calculated_percentage"] = "0.0000"
        if not internal:
            # Cliente: somente resultados finais. Não envia a memória ao renderizador.
            data["bdi"] = {"calculated_percentage": data["bdi"]["calculated_percentage"]}
            data["di"] = {
                "totals": {"total": data["di"]["totals"]["total"]},
                "rows": [
                    {
                        "key": row["key"], "item": row.get("item", row["key"]),
                        "discrimination": row["discrimination"],
                        "unit": row.get("unit", ""), "row_type": row.get("row_type", "ITEM"),
                        "values": {key: row["values"].get(key, "0")
                                   for key in ("quantity", "unit_price", "total")},
                    }
                    for row in data["di"]["rows"]
                ],
            }
    return data


def _export(sheet_id, audience, file_format, document="PLANILHA"):
    if audience not in ("CLIENT", "DARUIX"):
        raise ValidationError({"audience": "Use CLIENT ou DARUIX."})
    from .budget_export_renderers import (
        render_xlsx, render_pdf, render_pdf_bundle, pdf_filename_prefix, validate_pdf_selection,
    )
    if file_format == "pdf":
        try:
            validate_pdf_selection(audience, document)
        except ValueError as error:
            raise ValidationError({"document": str(error)}) from error
    sheet = _sheet_with_tree(sheet_id)
    _require_finalized(sheet)
    data = _export_data(
        sheet, audience,
        include_pdf_reports=audience == "DARUIX" and (
            file_format == "zip" or (file_format == "pdf" and document != "PLANILHA")
        ),
    )
    if file_format == "zip":
        return render_pdf_bundle(data), f"{pdf_filename_prefix(data)}-PDFS.zip"
    content = render_xlsx(data) if file_format == "xlsx" else render_pdf(data, document)
    import re
    budget_number = re.sub(r"[^A-Za-z0-9_.-]+", "-", data["number"] or "ORCAMENTO").strip(".") or "ORCAMENTO"
    suffix = "CLIENTE" if audience == "CLIENT" else "DARUIX"
    if file_format == "pdf":
        suffix += f"-{document}"
    return content, f"{budget_number}-R{sheet.revision:02d}-{suffix}.{file_format}"


def export_budget_sheet_xlsx(sheet_id: int, audience: ExportAudience) -> tuple[bytes, str]:
    return _export(sheet_id, audience, "xlsx")


def export_budget_sheet_pdf(
    sheet_id: int,
    audience: ExportAudience,
    document: PdfDocument = "PLANILHA",
) -> tuple[bytes, str]:
    return _export(sheet_id, audience, "pdf", document)


def export_budget_sheet_pdfs(sheet_id: int, audience: ExportAudience) -> tuple[bytes, str]:
    return _export(sheet_id, audience, "zip")
