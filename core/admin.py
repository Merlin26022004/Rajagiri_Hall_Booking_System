from django.contrib import admin
from .models import Space, Booking, BlockedDate, Bus, BusBooking

@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "location", "capacity", "managed_by")
    list_filter = ("type",)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("space", "date", "start_time", "end_time", "requested_by", "status")
    list_filter = ("status", "space", "date")
    search_fields = ("purpose", "requested_by__username")

@admin.register(BlockedDate)
class BlockedDateAdmin(admin.ModelAdmin):
    list_display = ("space", "date", "reason")
    list_filter = ("space", "date")

# === BUS MODELS ===
@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ("name", "number_plate", "capacity", "driver_name", "driver_phone")
    search_fields = ("name", "number_plate")

@admin.register(BusBooking)
class BusBookingAdmin(admin.ModelAdmin):
    # FIXED: Changed 'user' -> 'requested_by' and 'approval_status' -> 'status'
    list_display = ("bus", "requested_by", "date", "start_time", "destination", "status")
    list_filter = ("status", "date")
    search_fields = ("destination", "requested_by__username")