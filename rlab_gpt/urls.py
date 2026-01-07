from django.urls import path
from core import views

urlpatterns = [
    # Auth
    path("admin/login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Hall Pages
    path("", views.home, name="home"),
    path("halls/", views.hall_list, name="hall_list"),
    path("halls/<int:hall_id>/", views.hall_detail, name="hall_detail"),

    # Booking flow
    path("halls/<int:hall_id>/book/", views.book_hall, name="book_hall"),
    path("my-bookings/", views.my_bookings, name="my_bookings"),
    path(
        "my-bookings/<int:booking_id>/cancel/",
        views.cancel_booking,
        name="cancel_booking",
    ),

    # Admin Dashboard
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path(
        "admin/dashboard/bookings/<int:booking_id>/approve/",
        views.approve_booking,
        name="approve_booking",
    ),
    path(
        "admin/dashboard/bookings/<int:booking_id>/reject/",
        views.reject_booking,
        name="reject_booking",
    ),
    path(
        "admin/dashboard/bookings/<int:booking_id>/reschedule/",
        views.reschedule_booking,
        name="reschedule_booking",
    ),
    path("admin/users/", views.manage_users, name="manage_users"),
    path("admin/users/<int:user_id>/toggle/", views.toggle_user_status, name="toggle_user_status"),
    path("admin/audit-log/", views.view_audit_log, name="view_audit_log"),
    path("admin/blocked-dates/", views.manage_blocked_dates, name="manage_blocked_dates"),

    # API
    path(
        "api/unavailable-dates/",
        views.api_unavailable_dates,
        name="api_unavailable_dates",
    ),
]
