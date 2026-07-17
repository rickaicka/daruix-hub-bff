from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.services.session_service import validate_user_session


class SessionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        validate_user_session(
            user=user,
            token=validated_token,
            update_activity=True,
        )

        return user