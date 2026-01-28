from django.contrib import admin
from .models import Space, Booking, BlockedDate, Bus, BusBooking, Facility

# === NEW: Manage Facilities (Mic, Projector, etc.) ===
@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "location", "capacity", "managed_by")
    list_filter = ("type",)
    
    # === NEW: Easy selection box for Hall Facilities ===
    filter_horizontal = ('facilities',)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    # Added 'get_facilities' to see requests in the list
    list_display = ("space", "date", "start_time", "end_time", "requested_by", "status", "get_facilities")
    list_filter = ("status", "space", "date")
    search_fields = ("purpose", "requested_by__username")

    # Helper function to display ManyToMany field in list_display
    def get_facilities(self, obj):
        return ", ".join([f.name for f in obj.requested_facilities.all()])
    get_facilities.short_description = "Requested Facilities"

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
    list_display = ("bus", "requested_by", "date", "start_time", "destination", "status")
    list_filter = ("status", "date")
    search_fields = ("destination", "requested_by__username")