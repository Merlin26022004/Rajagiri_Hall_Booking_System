from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    # 🔹 Custom Admin Dashboard (must come BEFORE admin.site.urls)
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path(
        "admin/dashboard/bookings/<int:booking_id>/approve/",
        views.approve_booking,
        name="approve_booking",
    ),
    path("api/space-day-slots/", views.space_day_slots),

    path(
        "admin/dashboard/bookings/<int:booking_id>/reject/",
        views.reject_booking,
        name="reject_booking",
    ),
    path(
        "admin/dashboard/bookings/<int:booking_id>/cancel/",
        views.admin_cancel_booking,
        name="admin_cancel_booking",
    ),

    # Django's own admin site (keep this AFTER the custom /admin/dashboard/ paths)
    path("admin/", admin.site.urls),

    # Public pages
    path("", views.home, name="home"),
    path("spaces/", views.space_list, name="space_list"),
    path(
        "spaces/<int:space_id>/availability/",
        views.space_availability,
        name="space_availability",
    ),

    # Booking flow
    path("book/", views.book_space, name="book_space"),
    path("my-bookings/", views.my_bookings, name="my_bookings"),
    path(
        "my-bookings/<int:booking_id>/cancel/",
        views.cancel_booking,
        name="cancel_booking",
    ),

    # Logout
    path("logout/", views.logout_view, name="logout"),

    # API
    path(
        "api/unavailable-dates/",
        views.api_unavailable_dates,
        name="api_unavailable_dates",
    ),
]
