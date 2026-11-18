"""Ativação de senha do fornecedor sem expor tokens no frontend Angular."""
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods


def _get_user(uid, token):
    try:
        user = get_user_model().objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
        return None
    if (not user.is_active or user.user_type != "FORNECEDOR"
            or not hasattr(user, "supplier_profile") or not default_token_generator.check_token(user, token)):
        return None
    return user


@csrf_protect
@require_http_methods(["GET", "POST"])
def activate_supplier(request, uid, token):
    user = _get_user(uid, token)
    if user is None:
        return HttpResponse("Link inválido ou expirado. Solicite um novo convite ao comprador.", status=400)
    error = ""
    if request.method == "POST":
        password = request.POST.get("password", "")
        confirmation = request.POST.get("confirmation", "")
        if password != confirmation:
            error = "As senhas não conferem."
        else:
            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                error = " ".join(exc.messages)
            else:
                user.set_password(password)
                user.save(update_fields=["password"])
                return render(request, "quotation_maps/activate.html", {"complete": True, "username": user.username, "hub_public_url": getattr(settings, "HUB_PUBLIC_URL", "http://localhost:4300").rstrip("/")})
    return render(request, "quotation_maps/activate.html", {"username": user.username, "error": error})
