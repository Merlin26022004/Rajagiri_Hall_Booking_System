from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Q

# === NEW MODEL: VENUE TYPES (e.g., Class, Lab, Auditorium) ===
class SpaceType(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g. "Seminar Hall"

    def __str__(self):
        return self.name

# === FACILITIES (Mic, Projector, etc.) ===
class Facility(models.Model):
    name = models.CharField(max_length=100)  # e.g., "Projector", "Sound System"
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Facilities"


class Space(models.Model):
    name = models.CharField(max_length=100)
    
    # === FINAL: Dynamic Link to SpaceType ===
    type = models.ForeignKey(
        SpaceType, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='spaces'
    )
    
    location = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    
    # === Image Field for Dashboard ===
    image = models.ImageField(upload_to='spaces/', blank=True, null=True)

    # === Link Facilities to Space ===
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
        type_name = self.type.name if self.type else "Uncategorized"
        return f"{self.name} ({type_name})"


class Booking(models.Model):
    STATUS_PENDING = "Pending"
    STATUS_WAITLISTED = "Waitlisted" # <--- NEW STATUS
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CANCELLED = "Cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_WAITLISTED, "Waitlisted"), # <--- Added here
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
    
    # === User selects specific facilities for THIS booking ===
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

    # === NEW FIELDS FOR BUSINESS CLOCK LOGIC ===
    # Stores the calculated deadline (skipping weekends/holidays)
    approval_deadline = models.DateTimeField(null=True, blank=True)
    
    # Flags if the system auto-rejected this due to timeout
    auto_expired = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "start_time", "created_at"] # Added created_at to order queue

    def __str__(self):
        return f"{self.space.name} on {self.date} ({self.status})"

    # === QUEUE LOGIC ===
    @property
    def queue_position(self):
        """
        Returns the user's position in the queue for this specific slot.
        1 = Currently under review (Pending)
        2+ = Waitlisted behind others
        """
        # Find all active requests for this slot
        overlapping_bookings = Booking.objects.filter(
            space=self.space,
            date=self.date,
            status__in=[self.STATUS_PENDING, self.STATUS_WAITLISTED],
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).order_by('created_at')

        # Find where 'self' is in this list
        for index, booking in enumerate(overlapping_bookings):
            if booking.id == self.id:
                return index + 1 # 1-based index (1st, 2nd, 3rd...)
        return 0

    @property
    def current_holder(self):
        """
        Returns the User object of the person currently at Position #1 (Pending).
        Useful for Waitlisted users to know who is blocking them.
        """
        primary_booking = Booking.objects.filter(
            space=self.space,
            date=self.date,
            status=self.STATUS_PENDING,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).order_by('created_at').first()

        if primary_booking:
            return primary_booking.requested_by
        return None

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
        # Added WAITLISTED to allowed cancellation states
        return self.status in [self.STATUS_PENDING, self.STATUS_APPROVED, self.STATUS_WAITLISTED]


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
        now = timezone.localtime()
        
        if self.date < now.date():
            return False
            
        if self.date == now.date() and now.time() >= self.start_time:
            return False

        return self.status in [self.STATUS_PENDING, self.STATUS_APPROVED]