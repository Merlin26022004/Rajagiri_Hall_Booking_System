from django.conf import settings
from django.db import models
from django.utils import timezone


class Space(models.Model):
    HALL = "HALL"
    CLASSROOM = "CLASS"
    LAB = "LAB"

    TYPE_CHOICES = [
        (HALL, "Hall"),
        (CLASSROOM, "Classroom"),
        (LAB, "Lab"),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    location = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveIntegerField()
    description = models.TextField(blank=True)

    # HOD / Lab Incharge / Admin responsible
    managed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_spaces",
    )

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

    space = models.ForeignKey(
        Space, on_delete=models.CASCADE, related_name="bookings"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    purpose = models.TextField()
    expected_count = models.PositiveIntegerField()

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_bookings",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "start_time"]

    def __str__(self):
        return f"{self.space.name} on {self.date} ({self.status})"

    @property
    def can_cancel(self):
        today = timezone.localdate()
        return self.date >= today and self.status in [
            self.STATUS_PENDING,
            self.STATUS_APPROVED,
        ]


class BlockedDate(models.Model):
    space = models.ForeignKey(
        Space,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="blocked_dates",
    )
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("space", "date")

    def __str__(self):
        if self.space:
            return f"{self.space.name} blocked on {self.date}"
        return f"All spaces blocked on {self.date}"
