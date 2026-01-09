from .models import Notification

def user_notifications(request):
    if request.user.is_authenticated:
        # Get unread notifications for the logged-in user
        notifs = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')
        return {'user_notifications': notifs}
    return {}