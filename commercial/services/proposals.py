from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from commercial.models import Party, PartyType, Proposal, ProposalStatus


@transaction.atomic
def accept_proposal(*, proposal: Proposal) -> Proposal:
    proposal = Proposal.objects.select_for_update().select_related("party").get(pk=proposal.pk)
    if proposal.status == ProposalStatus.ACCEPTED:
        return proposal
    if proposal.status not in {ProposalStatus.SENT, ProposalStatus.BUDGETING}:
        raise ValidationError({"status": "Somente propostas enviadas ou em elaboração podem ser aceitas."})

    party = Party.objects.select_for_update().get(pk=proposal.party_id)
    now = timezone.now()
    if party.party_type == PartyType.INTERESTED:
        party.party_type = PartyType.CLIENT
        party.converted_at = now
        party.save(update_fields=("party_type", "converted_at", "updated_at"))

    proposal.status = ProposalStatus.ACCEPTED
    proposal.accepted_at = now
    proposal.save(update_fields=("status", "accepted_at", "updated_at"))
    return proposal
