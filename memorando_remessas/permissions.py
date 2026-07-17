from rest_framework.permissions import BasePermission

from accounts.services.permission_service import (
    user_has_any_permission,
    user_has_permission,
)


SHIPMENT_MEMO_VIEW_PERMISSION = "shipment_memo.view"
SHIPMENT_MEMO_CREATE_PERMISSION = "shipment_memo.create"
SHIPMENT_MEMO_UPDATE_PERMISSION = "shipment_memo.update"
SHIPMENT_MEMO_SEND_PERMISSION = "shipment_memo.send"
SHIPMENT_MEMO_CANCEL_PERMISSION = "shipment_memo.cancel"
SHIPMENT_MEMO_DELETE_PERMISSION = "shipment_memo.delete"
SHIPMENT_MEMO_MANAGE_OPTIONS_PERMISSION = (
    "shipment_memo.manage_options"
)
SHIPMENT_MEMO_BE_RESPONSIBLE_PERMISSION = (
    "shipment_memo.be_responsible"
)


class HasShipmentMemoFormAccess(BasePermission):
    message = (
        "Você não possui permissão para acessar "
        "os dados do formulário de memorando."
    )

    def has_permission(self, request, view):
        return user_has_any_permission(
            request.user,
            [
                SHIPMENT_MEMO_VIEW_PERMISSION,
                SHIPMENT_MEMO_CREATE_PERMISSION,
                SHIPMENT_MEMO_UPDATE_PERMISSION,
            ],
        )


class HasShipmentMemoViewPermission(BasePermission):
    message = (
        "Você não possui permissão para visualizar memorandos."
    )

    def has_permission(self, request, view):
        return user_has_permission(
            request.user,
            SHIPMENT_MEMO_VIEW_PERMISSION,
        )


class HasShipmentMemoCreatePermission(BasePermission):
    message = (
        "Você não possui permissão para criar memorandos."
    )

    def has_permission(self, request, view):
        return user_has_permission(
            request.user,
            SHIPMENT_MEMO_CREATE_PERMISSION,
        )


class HasShipmentMemoUpdatePermission(BasePermission):
    message = (
        "Você não possui permissão para alterar memorandos."
    )

    def has_permission(self, request, view):
        return user_has_permission(
            request.user,
            SHIPMENT_MEMO_UPDATE_PERMISSION,
        )


class HasShipmentMemoDeletePermission(BasePermission):
    message = (
        "Você não possui permissão para excluir memorandos."
    )

    def has_permission(self, request, view):
        return user_has_permission(
            request.user,
            SHIPMENT_MEMO_DELETE_PERMISSION,
        )

class HasShipmentMemoSendPermission(BasePermission):
    message = (
        "Você não possui permissão para enviar memorandos."
    )

    def has_permission(self, request, view):
        return user_has_permission(
            request.user,
            SHIPMENT_MEMO_SEND_PERMISSION,
        )


class HasShipmentMemoCancelPermission(BasePermission):
    message = (
        "Você não possui permissão para cancelar memorandos."
    )

    def has_permission(self, request, view):
        return user_has_permission(
            request.user,
            SHIPMENT_MEMO_CANCEL_PERMISSION,
        )