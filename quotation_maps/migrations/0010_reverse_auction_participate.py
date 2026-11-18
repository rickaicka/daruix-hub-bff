from django.db import migrations


PERMISSION = "reverse_auction.participate"
GROUP = "LEILAO_REVERSO_TEMPORARIO"


def configure(apps, schema_editor):
    alias = schema_editor.connection.alias
    Permission = apps.get_model("accounts", "Permission")
    UserGroup = apps.get_model("accounts", "UserGroup")
    GroupPermission = apps.get_model("accounts", "GroupPermission")
    User = apps.get_model("accounts", "User")
    Supplier = apps.get_model("quotation_maps", "Supplier")
    HubMenuItem = apps.get_model("accounts", "HubMenuItem")

    permission, _ = Permission.objects.using(alias).get_or_create(
        code=PERMISSION,
        defaults={"module": "reverse_auction", "description": "Participar de leilão reverso por convite", "is_active": True},
    )
    group, _ = UserGroup.objects.using(alias).get_or_create(
        user_type="FORNECEDOR", name=GROUP,
        defaults={"description": "Participação por convite temporário", "is_active": True},
    )
    GroupPermission.objects.using(alias).get_or_create(
        group=group, permission=permission, defaults={"is_active": True},
    )

    # Backfill apenas dos fornecedores vinculados aos mapas e sem grupo.
    user_ids = Supplier.objects.using(alias).filter(
        portal_profile__isnull=False, portal_profile__user__group__isnull=True,
        portal_profile__user__user_type="FORNECEDOR",
    ).values_list("portal_profile__user_id", flat=True)
    User.objects.using(alias).filter(pk__in=user_ids, group__isnull=True).update(group_id=group.pk)

    # A rota externa permanece válida; somente o item administrativo desaparece.
    HubMenuItem.objects.using(alias).filter(
        route__icontains="leilao-reverso",
    ).update(is_active=False, favoritable=False)


class Migration(migrations.Migration):
    dependencies = [
        ("quotation_maps", "0009_temporary_invitations_supplier_evaluation"),
        ("accounts", "0013_disable_rm_revise_and_clean_notifications"),
    ]
    operations = [migrations.RunPython(configure, migrations.RunPython.noop)]
