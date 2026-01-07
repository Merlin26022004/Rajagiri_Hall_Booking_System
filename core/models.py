from django.db import models
from django.utils import timezone

class CustomUser(models.Model):
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    RECEPTIONIST = "RECEPTIONIST"
    SUPER_ADMIN = "SUPER_ADMIN"

    ROLE_CHOICES = [
        (STUDENT, "Student"),
        (FACULTY, "Faculty"),
        (RECEPTIONIST, "Receptionist"),
        (SUPER_ADMIN, "Super Admin"),
    ]

    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=STUDENT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.role})"


class Hall(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    seating_capacity = models.PositiveIntegerField()
    facilities = models.TextField(help_text="List available facilities")
    typical_use_cases = models.TextField(blank=True)
    booking_considerations = models.TextField(blank=True)
    image_path = models.CharField(max_length=255, help_text="Path to static image (e.g. static/halls/image.jpg)")
    is_active = models.BooleanField(default=True)
    
    STATUS_AVAILABLE = "Available"
    STATUS_MAINTENANCE = "Maintenance"
    STATUS_RESERVED = "Reserved"
    
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_MAINTENANCE, "Under Maintenance"),
        (STATUS_RESERVED, "Reserved (Priority)"),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)

    def __str__(self):
        return self.name


class Booking(models.Model):
    STATUS_PENDING = "Pending"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CANCELLED = "Cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    # Renamed 'space' to 'hall' to match new terminology
    hall = models.ForeignKey(
        Hall, on_delete=models.CASCADE, related_name="bookings"
    )
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="bookings",
    )

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    purpose = models.TextField()
    expected_count = models.PositiveIntegerField()

    # New fields for better tracking
    cancellation_reason = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    approved_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_bookings",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "start_time"]
    
    def __str__(self):
        return f"{self.hall.name} on {self.date} ({self.status})"

    @property
    def can_cancel(self):
        today = timezone.localdate()
        return self.date >= today and self.status in [
            self.STATUS_PENDING,
            self.STATUS_APPROVED,
        ]


class BlockedDate(models.Model):
    hall = models.ForeignKey(
        Hall,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="blocked_dates",
    )
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("hall", "date")

    def __str__(self):
        if self.hall:
            return f"{self.hall.name} blocked on {self.date}"
        return f"All halls blocked on {self.date}"


class Notification(models.Model):
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="notifications"
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification for {self.user.full_name}: {self.message}"


class AuditLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user} - {self.action}"
