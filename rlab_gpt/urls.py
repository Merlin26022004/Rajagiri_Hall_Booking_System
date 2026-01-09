from django.contrib import admin
from django.urls import path, include  # <--- CHANGE 1: Import 'include'
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

    # Django's own admin site
    path("admin/", admin.site.urls),

    # 🔹 CHANGE 2: Add Standard Auth URLs (Login, Password Reset, etc.)
    # This enables the link {% url 'login' %} to work!
    path("accounts/", include("django.contrib.auth.urls")),

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

    # Logout (You can keep your custom one, or use the one inside 'accounts/')
    path("logout/", views.logout_view, name="logout"),

    # API
    path(
        "api/unavailable-dates/",
        views.api_unavailable_dates,
        name="api_unavailable_dates",
    ),
    path('calendar/', views.calendar_view, name='calendar'),
    path('api/bookings/', views.api_bookings, name='api_bookings'),
    path('notifications/read/<int:notif_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/', views.notification_list, name='notification_list'),
]