"""Credenciais isoladas por convite, sem alterar autenticação global do Hub."""
import hashlib
import secrets
from datetime import timedelta
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions, serializers, throttling
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response
from .models import TenderBid
from accounts.services.permission_service import user_has_permission

DURATION = timedelta(hours=72)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_credential(bid):
    password = secrets.token_urlsafe(18)
    token = secrets.token_urlsafe(32)
    bid.temp_username = f"mc{bid.quotation_id}-f{bid.supplier_id}"
    bid.temp_password_hash = make_password(password)
    bid.invitation_token_hash = digest(token)
    bid.access_token_hash = ""
    bid.invited_at = timezone.now()
    bid.expires_at = bid.invited_at + DURATION
    bid.revoked_at = None
    bid.emailed_at = None
    bid.email_error = ""
    bid.save(update_fields=["temp_username", "temp_password_hash", "invitation_token_hash", "access_token_hash", "invited_at", "expires_at", "revoked_at", "emailed_at", "email_error"])
    return password, token


def is_valid(bid):
    q = bid.quotation
    now = timezone.now()
    return (bid.revoked_at is None and bid.expires_at is not None and bid.expires_at > now
            and q.status == q.Status.DRAFT and q.tender_opened_at is not None
            and q.tender_closed_at is None and q.tender_deadline is not None
            and q.tender_deadline > now and bid.supplier.active)


class InvitationAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("ascii", errors="ignore")
        if not header.startswith("Invitation "):
            return None
        token = header[len("Invitation "):].strip()
        if not token or len(token) > 256:
            raise exceptions.AuthenticationFailed("Credencial inválida.")
        bid = (TenderBid.objects.select_related("quotation", "supplier", "supplier__portal_profile__user")
               .filter(access_token_hash=digest(token)).first())
        if bid is None or not is_valid(bid):
            raise exceptions.AuthenticationFailed("Convite expirado ou revogado.")
        if bid.supplier.portal_profile is None or not bid.supplier.portal_profile.user.is_active:
            raise exceptions.AuthenticationFailed("Fornecedor sem conta ativa.")
        user = bid.supplier.portal_profile.user
        if not user_has_permission(user, "reverse_auction.participate"):
            raise exceptions.PermissionDenied("Sem permissão para participar do leilão reverso.")
        return user, bid


class InvitationOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.auth and isinstance(request.auth, TenderBid)
            and is_valid(request.auth)
            and user_has_permission(request.user, "reverse_auction.participate")
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=120)
    password = serializers.CharField(write_only=True)
    invitation_token = serializers.CharField(max_length=256)


class InvitationLoginThrottle(throttling.AnonRateThrottle):
    rate = "5/min"


@api_view(["POST"])
@throttle_classes([InvitationLoginThrottle])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def login_invitation(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    bid = (TenderBid.objects.select_related("quotation", "supplier")
           .filter(temp_username=values["username"], invitation_token_hash=digest(values["invitation_token"]))
           .first())
    if bid is None or not is_valid(bid) or not check_password(values["password"], bid.temp_password_hash):
        raise exceptions.AuthenticationFailed("Convite inválido, encerrado ou expirado.")
    user = bid.supplier.portal_profile.user if bid.supplier.portal_profile_id else None
    if not user or not user_has_permission(user, "reverse_auction.participate"):
        raise exceptions.PermissionDenied("Fornecedor sem permissão de participação.")
    # Um novo login revoga imediatamente o token da sessão anterior.
    token = secrets.token_urlsafe(40)
    bid.access_token_hash = digest(token)
    bid.save(update_fields=["access_token_hash"])
    return Response({"access_token": token, "token_type": "Invitation", "expires_at": bid.expires_at,
                     "quotation_id": bid.quotation_id, "supplier_id": bid.supplier_id})
