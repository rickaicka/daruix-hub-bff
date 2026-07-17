from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from memorando_remessas.models import (
    ShipmentMemoFile,
)


@receiver(
    post_delete,
    sender=ShipmentMemoFile,
)
def delete_shipment_memo_physical_file(
    sender,
    instance,
    **kwargs,
):
    if not instance.file:
        return

    file_name = instance.file.name
    storage = instance.file.storage

    if not file_name:
        return

    def delete_file_after_commit():
        if storage.exists(file_name):
            storage.delete(file_name)

    transaction.on_commit(
        delete_file_after_commit
    )