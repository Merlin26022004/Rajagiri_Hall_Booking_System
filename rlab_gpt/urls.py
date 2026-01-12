from django.contrib import admin
from django.urls import path, include
from core import views

urlpatterns = [
    # --- 1. Custom Admin Paths (MUST be before admin.site.urls) ---
    path('admin/timetable/', views.upload_timetable, name='upload_timetable'),
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Dashboard Actions
    path('admin/dashboard/bookings/<int:booking_id>/approve/', views.approve_booking, name='approve_booking'),
    path('admin/dashboard/bookings/<int:booking_id>/reject/', views.reject_booking, name='reject_booking'),
    path('admin/dashboard/bookings/<int:booking_id>/cancel/', views.admin_cancel_booking, name='admin_cancel_booking'),

    # --- 2. Standard Admin Path ---
    path('admin/', admin.site.urls),

    # --- 3. Authentication ---
    # Custom Login/Logout
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    # Standard Django auth for password reset etc (optional)
    path('accounts/', include('django.contrib.auth.urls')),

    # --- 4. Main App Paths ---
    path('', views.home, name='home'),
    path('spaces/', views.space_list, name='space_list'),
    path('spaces/<int:space_id>/availability/', views.space_availability, name='space_availability'),

    # Transport / Bus
    path('buses/', views.bus_list, name='bus_list'),
    path('buses/book/', views.book_bus, name='book_bus'),

    # Booking
    path('book/', views.book_space, name='book_space'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('my-bookings/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),

    # Calendar & API
    path('calendar/', views.calendar_view, name='calendar'),
    path('api/bookings/', views.api_bookings, name='api_bookings'),
    path('api/unavailable-dates/', views.api_unavailable_dates, name='api_unavailable_dates'),
    path('api/space-day-slots/', views.space_day_slots, name='space_day_slots'),

    # Notifications
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/read/<int:notif_id>/', views.mark_notification_read, name='mark_notification_read'),
]