from django.contrib import admin
from .models import Space, Booking, BlockedDate


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
