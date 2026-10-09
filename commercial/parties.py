from typing import Any

from django.db import transaction

from commercial.models import (
    Address,
    CatalogOrigin,
    Contact,
    Party,
    PartyType,
)


class PartyChildNotFoundError(ValueError):
    pass


def _update_model_fields(
    instance,
    values: dict[str, Any],
) -> None:
    changed_fields: list[str] = []

    for field, value in values.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed_fields.append(field)

    if changed_fields:
        instance.save(
            update_fields=(
                *changed_fields,
                "updated_at",
            )
        )


def _sync_addresses(
    *,
    party: Party,
    items: list[dict[str, Any]],
) -> None:
    existing = {
        item.pk: item
        for item in party.addresses.all()
    }

    received_ids: set[int] = set()
    primary_id: int | None = None

    for raw in items:
        values = dict(raw)
        address_id = values.pop("id", None)

        if address_id is None:
            address = Address.objects.create(
                party=party,
                **values,
            )
        else:
            address = existing.get(
                address_id
            )

            if address is None:
                raise PartyChildNotFoundError(
                    "Endereço não pertence ao cliente informado."
                )

            _update_model_fields(
                address,
                values,
            )

        received_ids.add(
            address.pk
        )

        if address.is_primary:
            primary_id = address.pk

    # A lista enviada representa o estado completo dos endereços.
    # Registros que deixaram de vir são inativados em vez de apagados.
    party.addresses.filter(
        is_active=True,
    ).exclude(
        pk__in=received_ids,
    ).update(
        is_active=False
    )

    if primary_id is not None:
        party.addresses.exclude(
            pk=primary_id
        ).filter(
            is_primary=True
        ).update(
            is_primary=False
        )


def _sync_contacts(
    *,
    party: Party,
    items: list[dict[str, Any]],
) -> None:
    existing = {
        item.pk: item
        for item in party.contacts.all()
    }

    received_ids: set[int] = set()
    primary_id: int | None = None

    for raw in items:
        values = dict(raw)
        contact_id = values.pop("id", None)

        if contact_id is None:
            contact = Contact.objects.create(
                party=party,
                **values,
            )
        else:
            contact = existing.get(
                contact_id
            )

            if contact is None:
                raise PartyChildNotFoundError(
                    "Contato não pertence ao cliente informado."
                )

            _update_model_fields(
                contact,
                values,
            )

        received_ids.add(
            contact.pk
        )

        if contact.is_primary:
            primary_id = contact.pk

    party.contacts.filter(
        is_active=True,
    ).exclude(
        pk__in=received_ids,
    ).update(
        is_active=False
    )

    if primary_id is not None:
        party.contacts.exclude(
            pk=primary_id
        ).filter(
            is_primary=True
        ).update(
            is_primary=False
        )


@transaction.atomic
def create_client_full(
    *,
    validated_data: dict[str, Any],
    user,
) -> Party:
    addresses = validated_data.pop(
        "addresses",
        [],
    )

    contacts = validated_data.pop(
        "contacts",
        [],
    )

    validated_data["party_type"] = (
        PartyType.CLIENT
    )

    validated_data["origin"] = (
        CatalogOrigin.HUB
    )

    party = Party.objects.create(
        created_by=user,
        updated_by=user,
        **validated_data,
    )

    if addresses:
        _sync_addresses(
            party=party,
            items=addresses,
        )

    if contacts:
        _sync_contacts(
            party=party,
            items=contacts,
        )

    return party


@transaction.atomic
def update_client_full(
    *,
    instance: Party,
    validated_data: dict[str, Any],
    user,
) -> Party:
    addresses_present = (
        "addresses" in validated_data
    )

    contacts_present = (
        "contacts" in validated_data
    )

    addresses = validated_data.pop(
        "addresses",
        [],
    )

    contacts = validated_data.pop(
        "contacts",
        [],
    )

    # O endpoint /clients/... não pode transformar o registro
    # em interessado.
    validated_data["party_type"] = (
        PartyType.CLIENT
    )

    validated_data["updated_by"] = user

    _update_model_fields(
        instance,
        validated_data,
    )

    if addresses_present:
        _sync_addresses(
            party=instance,
            items=addresses,
        )

    if contacts_present:
        _sync_contacts(
            party=instance,
            items=contacts,
        )

    return instance
