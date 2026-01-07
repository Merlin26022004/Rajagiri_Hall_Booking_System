from .models import Notification, CustomUser, AuditLog

def create_notification(user, message):
    Notification.objects.create(user=user, message=message)

def log_action(user, action):
    AuditLog.objects.create(user=user, action=action)

def notify_admins(message):
    admins = CustomUser.objects.filter(role__in=[CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN])
    for admin in admins:
        create_notification(admin, message)
