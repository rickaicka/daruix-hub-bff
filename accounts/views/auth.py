from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.services.auth_payload_service import build_login_user_payload
from accounts.legacy.legacy_auth_client import LegacyAuthClient, LegacyAuthError
from accounts.serializers.auth import (
    LoginResponseSerializer,
    LoginSerializer,
    LogoutResponseSerializer,
    LogoutSerializer,
    MeResponseSerializer,
)
from accounts.services.auth_payload_service import build_authenticated_user_payload
from accounts.services.legacy_import_service import LegacyImportService

User = get_user_model()


def authenticate_django_user(request, username: str, password: str):
    return authenticate(
        request=request,
        username=username,
        password=password,
    )


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Login",
        description=(
            "Authenticates a SGOWEB user by username and password. "
            "First tries the Django database. If authentication fails, "
            "it can try the legacy Access authentication bridge."
        ),
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            401: OpenApiResponse(description="Invalid username or password."),
            403: OpenApiResponse(description="User is inactive."),
            503: OpenApiResponse(description="Legacy authentication unavailable."),
        },
        examples=[
            OpenApiExample(
                name="Login request",
                value={
                    "username": "ricardo",
                    "password": "123456",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Successful login",
                value={
                    "access_token": "jwt-access-token",
                    "refresh_token": "jwt-refresh-token",
                    "token_type": "bearer",
                    "usuario": {
                        "id_usuario": 1,
                        "username": "ricardo",
                        "nome": "Ricardo Salim Daruix",
                        "email": "ricardo@daruix.com.br",
                        "tipo_usuario": "COLABORADOR",
                        "grupo": "DIRETORIA",
                        "permissoes": [
                            "proposal.view",
                            "purchase_order.approve",
                        ],
                    },
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = authenticate_django_user(
            request=request,
            username=username,
            password=password,
        )

        if not user:
            try:
                user = self._try_legacy_login(username, password)
            except LegacyAuthError as error:
                return Response(
                    {"detail": str(error)},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        if not user:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "User is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_payload = build_login_user_payload(user)

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "token_type": "bearer",
                "usuario": user_payload,
            },
            status=status.HTTP_200_OK,
        )

    def _try_legacy_login(self, username: str, password: str):
        legacy_client = LegacyAuthClient()
        legacy_payload = legacy_client.authenticate(username, password)

        print("LEGACY PAYLOAD:", legacy_payload)

        if not legacy_payload:
            return None

        import_service = LegacyImportService()

        return import_service.import_user_from_legacy_payload(
            payload=legacy_payload,
            raw_password=password,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Usuário autenticado",
        description="Retorna os dados completos do usuário autenticado, incluindo grupo e permissões quando existirem.",
        responses={
            200: MeResponseSerializer,
            401: OpenApiResponse(description="Credenciais de autenticação não foram informadas."),
        },
    )
    def get(self, request):
        return Response(
            build_authenticated_user_payload(request.user),
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Logout",
        description="Blacklists the provided refresh token.",
        request=LogoutSerializer,
        responses={
            200: LogoutResponseSerializer,
            400: OpenApiResponse(description="Invalid or expired refresh token."),
        },
        examples=[
            OpenApiExample(
                name="Logout request",
                value={
                    "refresh_token": "jwt-refresh-token",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Logout response",
                value={
                    "detail": "Logout completed successfully.",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh_token"]

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"detail": "Logout completed successfully."},
                status=status.HTTP_200_OK,
            )

        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )