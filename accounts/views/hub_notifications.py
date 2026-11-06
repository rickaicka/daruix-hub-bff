from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.models import HubNotification


def serialize(n):
    return {'id': n.pk, 'kind': n.kind, 'title': n.title, 'message': n.message,
            'route': n.route, 'module': n.module, 'event': n.event,
            'resource_type': n.resource_type, 'resource_id': n.resource_id,
            'payload': n.payload, 'created_at': n.created_at.isoformat(),
            'read': bool(n.read_at)}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_list(request):
    qs = HubNotification.objects.filter(recipient=request.user, resolved_at__isnull=True)
    unread = qs.filter(read_at__isnull=True).count()
    return Response({'unread': unread, 'results': [serialize(n) for n in qs[:50]]})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def notification_read(request, pk):
    n = get_object_or_404(HubNotification, pk=pk, recipient=request.user)
    if n.read_at is None:
        n.read_at = timezone.now()
        n.save(update_fields=['read_at'])
    return Response({'ok': True})
