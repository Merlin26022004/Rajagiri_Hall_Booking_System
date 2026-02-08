from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

# === NEW MODEL: FACILITIES (Mic, Projector, etc.) ===
class Facility(models.Model):
    name = models.CharField(max_length=100)  # e.g., "Projector", "Sound System"
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Facilities"


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
    
    # === NEW: Image Field for Dashboard ===
    # Requires Pillow library: pip install Pillow
    image = models.ImageField(upload_to='spaces/', blank=True, null=True)

    # === NEW: Link Facilities to Space ===
    # Defines what equipment this specific hall HAS.
    facilities = models.ManyToManyField(Facility, blank=True, related_name="spaces")

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

    # Stores the Faculty Name for Student Bookings
    faculty_in_charge = models.CharField(max_length=150, blank=True, null=True)
    
    # === NEW: User selects specific facilities for THIS booking ===
    requested_facilities = models.ManyToManyField(Facility, blank=True)

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

    # === TIME-AWARE CANCELLATION ===
    @property
    def can_cancel(self):
        """
        Allows cancellation ONLY if:
        1. Date is in the future.
        2. Date is TODAY but Start Time hasn't passed yet.
        """
        now = timezone.localtime()
        
        # 1. Past Date -> Cannot Cancel
        if self.date < now.date():
            return False
            
        # 2. Today -> Check Time
        if self.date == now.date() and now.time() >= self.start_time:
            return False

        # 3. Future/Valid Time -> Check Status
        return self.status in [self.STATUS_PENDING, self.STATUS_APPROVED]


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

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"
    
# ================= BUS MANAGEMENT =================

class Bus(models.Model):
    name = models.CharField(max_length=100)  # e.g., "Bus No. 12"
    number_plate = models.CharField(max_length=20)
    driver_name = models.CharField(max_length=100)
    driver_phone = models.CharField(max_length=15)
    capacity = models.IntegerField()
    
    class Meta:
        verbose_name_plural = "Buses"

    def __str__(self):
        return f"{self.name} ({self.number_plate})"

class BusBooking(models.Model):
    STATUS_PENDING = 'Pending'
    STATUS_APPROVED = 'Approved'
    STATUS_REJECTED = 'Rejected'
    STATUS_CANCELLED = 'Cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bus_requests')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    origin = models.CharField(max_length=200, default="College Campus")
    destination = models.CharField(max_length=255) # Specific to buses
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bus {self.bus.name} for {self.destination}"

    # === TIME-AWARE CANCELLATION ===
    @property
    def can_cancel(self):
        """
        Allows cancellation ONLY if:
        1. Date is in the future.
        2. Date is TODAY but Start Time hasn't passed yet.
        """
        now = timezone.localtime()
        
        # 1. Past Date -> Cannot Cancel
        if self.date < now.date():
            return False
            
        # 2. Today -> Check Time
        if self.date == now.date() and now.time() >= self.start_time:
            return False

        # 3. Future/Valid Time -> Check Status
        return self.status in [self.STATUS_PENDING, self.STATUS_APPROVED]