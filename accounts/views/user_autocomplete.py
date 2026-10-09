from django.contrib.auth import get_user_model
from django.db.models import Q

from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from accounts.models.choices import UserType


User = get_user_model()


class UserAutocompleteSerializer(
    serializers.ModelSerializer
):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "name",
            "email",
        )

    def get_name(self, obj):
        return (
            obj.name
            or obj.username
        )


class UserAutocompletePagination(
    PageNumberPagination
):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class UserAutocompleteView(
    generics.ListAPIView
):
    serializer_class = (
        UserAutocompleteSerializer
    )

    pagination_class = (
        UserAutocompletePagination
    )

    permission_classes = (
        IsAuthenticated,
    )

    def get_queryset(self):
        queryset = (
            User.objects
            .filter(
                is_active=True,
                user_type=UserType.EMPLOYEE,
            )
            .order_by(
                "name",
                "id",
            )
        )

        term = (
            self.request
            .query_params
            .get(
                "search",
                "",
            )
            .strip()
        )

        if term:
            queryset = queryset.filter(
                Q(
                    name__icontains=term
                )
                |
                Q(
                    username__icontains=term
                )
                |
                Q(
                    email__icontains=term
                )
            )

        return queryset