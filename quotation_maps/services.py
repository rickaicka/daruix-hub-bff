from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from commercial.models import Proposal

from accounts.services.notifications import publish, resolve
from accounts.services.permission_service import user_has_permission
from material_requisitions.models import MaterialRequisitionItem

from .models import QuotationMap


ROUTE = "/hub/obras/mapas-cotacao"
PERMISSION = "quotation_map.manage"


@transaction.atomic
def create_for_approval(revision):
    rm = revision.requisition
    proposal = Proposal.objects.select_for_update().get(pk=rm.proposal_id)
    existing = QuotationMap.objects.filter(requisition=rm).first()
    if existing is not None:
        return existing, False
    pc = proposal.code.removeprefix("PC")
    last = QuotationMap.objects.filter(requisition__proposal=proposal).aggregate(value=Max("revision_number"))["value"]
    number = 0 if last is None else last + 1
    items = MaterialRequisitionItem.objects.filter(section__revision=revision).select_related("section")
    snapshot = [
        dict(id=item.pk, stage=item.section.stage_name, description=item.description, unit=item.unit,
             quantity=str(item.quantity), period=item.period, period_unit=item.period_unit, notes=item.notes)
        for item in items.order_by("section__position", "section_id", "position", "pk")
    ]
    return QuotationMap.objects.get_or_create(
        requisition=rm,
        defaults=dict(approved_revision=revision, code=f"MC{pc}" if number == 0 else f"MC{pc}-{number:02d}", revision_number=number, items=snapshot),
    )


@transaction.atomic
def notify_ready(map_id, actor_id):
    quotation = QuotationMap.objects.select_for_update().filter(pk=map_id, status=QuotationMap.Status.READY).first()
    if quotation is None:
        return
    users = get_user_model().objects.filter(is_active=True, user_type="COLABORADOR").select_related("group")
    publish(module="obras", event="quotation_map.ready", resource_type="quotation_map",
            resource_id=map_id, title="RM aprovada · Montar cotação", message=quotation.code,
            recipients=[user for user in users if can_manage(user)], actor=actor_id,
            route=f"{ROUTE}?mapa={map_id}", payload={"requisition_id": quotation.requisition_id})


def can_manage(user):
    return user.is_authenticated and user.is_active and user.user_type == "COLABORADOR" and (
        user.is_superuser or (
            user.group_id and user.group.is_active
            and user_has_permission(user, PERMISSION)
        )
    )


def resolve_ready(map_id):
    resolve(module="obras", event="quotation_map.ready", resource_type="quotation_map", resource_id=map_id)


def cancel_for_rm(rm):
    quotation = QuotationMap.objects.select_for_update().filter(requisition=rm).first()
    if quotation is None or quotation.status == QuotationMap.Status.ORDERED:
        return
    quotation.status = QuotationMap.Status.CANCELLED
    quotation.version += 1
    quotation.save(update_fields=["status", "version"])
    resolve_ready(quotation.pk)
