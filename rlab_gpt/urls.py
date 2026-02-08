from django.contrib import admin
from django.urls import path, include
from core import views

urlpatterns = [
    # --- 1. Custom Admin Paths ---
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # NEW: Full History Page
    path('admin/history/', views.booking_history, name='booking_history'),

    # Timetable Management
    path('admin/timetable/', views.upload_timetable, name='upload_timetable'),
    path('admin/timetable/clear/', views.clear_timetable, name='clear_timetable'),
    
    # Dashboard Actions (Booking Management)
    path('admin/dashboard/bookings/<int:booking_id>/approve/', views.approve_booking, name='approve_booking'),
    path('admin/dashboard/bookings/<int:booking_id>/reject/', views.reject_booking, name='reject_booking'),
    path('admin/dashboard/bookings/<int:booking_id>/cancel/', views.admin_cancel_booking, name='admin_cancel_booking'),

    # Dashboard Actions (User Management)
    path('admin/dashboard/users/<int:user_id>/assign/', views.assign_role, name='assign_role'),
    # NEW: Reject/Delete User Action
    path('admin/dashboard/users/<int:user_id>/reject/', views.reject_user, name='reject_user'),

    # --- 2. Standard Admin Path ---
    # This handles the Superuser login automatically
    path('admin/', admin.site.urls),

    # --- 3. Authentication ---
    # ⚠️ REPLACED: "django.contrib.auth.urls" with "allauth.urls"
    # This enables http://localhost:8000/accounts/google/login/
    path('accounts/', include('allauth.urls')),

    # Custom Login Page
    path('login/', views.login_view, name='login'),
    
    # Custom Logout
    path('logout/', views.logout_view, name='logout'),

    # --- 4. Main App Paths ---
    path('', views.home, name='home'),
    path('spaces/', views.space_list, name='space_list'),
    path('spaces/<int:space_id>/availability/', views.space_availability, name='space_availability'),

    # Transport / Bus
    path('buses/', views.bus_list, name='bus_list'),
    path('buses/book/', views.book_bus, name='book_bus'),
    path('buses/approve/<int:booking_id>/', views.approve_bus_booking, name='approve_bus_booking'),
    path('buses/reject/<int:booking_id>/', views.reject_bus_booking, name='reject_bus_booking'),
    path('buses/cancel/<int:booking_id>/', views.cancel_bus_booking, name='cancel_bus_booking'),

    # Booking
    path('book/', views.book_space, name='book_space'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('my-bookings/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),

    # Calendar & API
    path('calendar/', views.calendar_view, name='calendar'),
    path('api/bookings/', views.api_bookings, name='api_bookings'),
    path('api/unavailable-dates/', views.api_unavailable_dates, name='api_unavailable_dates'),
    
    # Facilities API
    path('api/space-facilities/', views.api_space_facilities, name='api_space_facilities'),
    path('api/space-day-slots/', views.space_day_slots, name='space_day_slots'),

    # Notifications
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/read/<int:notif_id>/', views.mark_notification_read, name='mark_notification_read'),
]