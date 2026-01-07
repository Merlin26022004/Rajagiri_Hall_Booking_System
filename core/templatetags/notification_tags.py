from django import template
from core.models import Notification

register = template.Library()

@register.simple_tag
def get_unread_notifications(user):
    # Ensure user is a CustomUser instance or has an id (if using session user dict fallback)
    # But get_current_user returns an object.
    if not user or not hasattr(user, 'id'):
        return []
    return Notification.objects.filter(user=user, is_read=False)[:5]
