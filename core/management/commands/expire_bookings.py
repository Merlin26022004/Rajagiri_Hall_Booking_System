from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Booking, Notification 
from core.views import send_notification_email 

class Command(BaseCommand):
    help = 'Auto-reject bookings that passed their approval deadline'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        
        # Find bookings that are PENDING, have a deadline, and deadline < now
        expired_bookings = Booking.objects.filter(
            status=Booking.STATUS_PENDING,
            approval_deadline__lt=now,
            auto_expired=False
        )

        count = 0
        for booking in expired_bookings:
            # 1. Update Status
            booking.status = Booking.STATUS_REJECTED
            booking.auto_expired = True # Flag so we know system did it
            booking.save()
            
            # 2. Notify User
            msg = f"Your booking for {booking.space.name} on {booking.date} EXPIRED because it was not approved within the 24-hour business window."
            
            Notification.objects.create(
                user=booking.requested_by,
                message="SYSTEM: Booking Request Expired"
            )
            
            if booking.requested_by.email:
                send_notification_email(
                    subject="Booking Request Expired",
                    message=msg,
                    recipients=[booking.requested_by.email],
                    context_type="hall"
                )
            
            count += 1
            self.stdout.write(self.style.WARNING(f'Expired booking {booking.id} for {booking.requested_by.username}'))

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No expired bookings found.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully expired {count} bookings'))