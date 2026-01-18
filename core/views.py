import json
from datetime import timedelta, date
from django.contrib import messages
from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User, Group
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.conf import settings

from .models import Space, Booking, BlockedDate, Notification, Bus, BusBooking

# ================= Helpers =================

def is_admin_user(user):
    """Who can see the custom admin dashboard & approve bookings."""
    return user.is_staff or user.is_superuser

def is_transport_officer(user):
    """Check if user belongs to the 'Transport' group."""
    return user.groups.filter(name='Transport').exists()

def send_notification_email(subject, message, recipients, context_type="hall"):
    """
    Sends email with dynamic sender name based on context.
    context_type: 'hall' (default) or 'bus'
    """
    if not recipients:
        return

    # Dynamic Sender Name Logic
    sender_email = settings.EMAIL_HOST_USER
    if context_type == "hall":
        from_email = f"Rajagiri Facility Management <{sender_email}>"
    elif context_type == "bus":
        from_email = f"Rajagiri Transport Officer <{sender_email}>"
    else:
        from_email = sender_email

    try:
        send_mail(
            subject,
            message,
            from_email,
            recipients,
            fail_silently=True, # Keeps app running even if email fails
        )
    except Exception as e:
        print(f"Email Error: {e}")

# ================= Public / Home / Spaces =================

def home(request):
    """Homepage with hero + personalized snapshot stats."""
    
    # === SMART REDIRECT ===
    # If Transport Officer logs in, send them straight to Bus Dashboard.
    if request.user.is_authenticated and is_transport_officer(request.user):
        return redirect('bus_list')

    spaces = Space.objects.all()[:6]
    today = timezone.localdate()
    
    # Default stats
    today_total = 0
    pending = 0
    week_approved = 0
    blocked = BlockedDate.objects.filter(date__gte=today).count()

    if request.user.is_authenticated:
        if request.user.is_staff:
            # === ADMIN VIEW: GLOBAL ACTIVITY ===
            today_total = Booking.objects.filter(date=today).count()
            pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()
            week_approved = Booking.objects.filter(
                status=Booking.STATUS_APPROVED,
                date__range=[today, today + timedelta(days=6)]
            ).count()
        else:
            # === STUDENT VIEW: PERSONAL ACTIVITY ===
            today_total = Booking.objects.filter(requested_by=request.user, date=today).count()
            pending = Booking.objects.filter(requested_by=request.user, status=Booking.STATUS_PENDING).count()
            week_approved = Booking.objects.filter(
                requested_by=request.user,
                status=Booking.STATUS_APPROVED,
                date__range=[today, today + timedelta(days=6)]
            ).count()

    stats = {
        "today_total": today_total,
        "pending": pending,
        "week_approved": week_approved,
        "blocked": blocked,
    }

    return render(request, "index.html", {"spaces": spaces, "stats": stats})

def space_list(request):
    return render(request, "spaces.html", {"spaces": Space.objects.all()})

def space_availability(request, space_id):
    space = get_object_or_404(Space, pk=space_id)
    today = timezone.localdate()

    bookings = (
        Booking.objects.filter(space=space, date__gte=today)
        .order_by("date", "start_time")
        .select_related("requested_by", "approved_by")
    )
    
    blocked_dates = BlockedDate.objects.filter(
        Q(space=space) | Q(space__isnull=True),
        date__gte=today,
    ).order_by("date")

    return render(request, "space_availability.html", {
        "space": space, "bookings": bookings, "blocked_dates": blocked_dates
    })

# ================= Booking Logic =================

@login_required
def book_space(request):
    spaces = Space.objects.all()
    selected_space_id = request.GET.get("space_id")
    selected_space = None

    if selected_space_id:
        try:
            selected_space = Space.objects.get(id=selected_space_id)
        except Space.DoesNotExist:
            pass

    if request.method == "POST":
        space_id = request.POST.get("space_id")
        date_str = request.POST.get("date")
        start_time_str = request.POST.get("start_time")
        end_time_str = request.POST.get("end_time")
        expected_count = request.POST.get("expected_count")
        purpose = request.POST.get("purpose")
        
        # NEW: Capture Faculty Name for Student Bookings
        faculty_name = request.POST.get("faculty_in_charge")

        if not all([space_id, date_str, start_time_str, end_time_str, expected_count, purpose]):
            messages.error(request, "Please fill all required fields.")
            return redirect("book_space")

        # NEW VALIDATION: Students MUST provide a Faculty Name
        if not request.user.is_staff and not faculty_name:
            messages.error(request, "Students must specify the Faculty In-Charge who approved this.")
            return redirect("book_space")

        space = get_object_or_404(Space, id=space_id)

        try:
            expected_count_int = int(expected_count)
            if expected_count_int > space.capacity:
                messages.error(request, "Expected count exceeds space capacity.")
                return redirect("book_space")
        except ValueError:
            messages.error(request, "Expected count must be a number.")
            return redirect("book_space")

        d = parse_date(date_str)
        st = parse_time(start_time_str)
        et = parse_time(end_time_str)

        if d < timezone.localdate():
            messages.error(request, "You cannot book a date in the past.")
            return redirect("book_space")

        if not (d and st and et) or et <= st:
            messages.error(request, "Invalid date or time range.")
            return redirect("book_space")

        if BlockedDate.objects.filter(Q(space=space) | Q(space__isnull=True), date=d).exists():
            messages.error(request, "This date is blocked.")
            return redirect("book_space")

        conflict = Booking.objects.filter(
            space=space, date=d,
            status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED]
        ).filter(Q(start_time__lt=et, end_time__gt=st)).exists()

        if conflict:
            messages.error(request, "Time slot conflicts with an existing booking.")
            return redirect("book_space")

        # === 2. SMART LOGIC: Auto-Approve for EVERYONE ===
        # Policy Change: Students are now auto-approved if they provide a reference.
        booking_status = Booking.STATUS_APPROVED
        
        # If Staff, they approved it themselves. If Student, system auto-approves (no system admin ID linked).
        approver = request.user if request.user.is_staff else None

        Booking.objects.create(
            space=space, requested_by=request.user, date=d,
            start_time=st, end_time=et,
            expected_count=expected_count_int, purpose=purpose,
            status=booking_status, approved_by=approver,
            faculty_in_charge=faculty_name # <--- Saving the reference name
        )

        # === 3. SMART NOTIFICATIONS ===
        
        # Identify Real Admins (Superusers) to receive alerts
        facility_admins = User.objects.filter(is_superuser=True).exclude(id=request.user.id)
        admin_emails = [u.email for u in facility_admins if u.email]

        if request.user.is_staff:
            # === A. STAFF/FACULTY BOOKING ===
            
            # 1. Send Confirmation to the Booker (Faculty)
            if request.user.email:
                send_notification_email(
                    subject="Booking Confirmed",
                    message=f"Dear {request.user.username},\n\nYour booking for {space.name} on {d} has been successfully confirmed.\n\nTime: {st} to {et}\nPurpose: {purpose}",
                    recipients=[request.user.email],
                    context_type="hall"
                )
            
            # 2. Alert Admins
            if admin_emails:
                send_notification_email(
                    subject=f"New Booking Alert: {space.name}",
                    message=f"ALERT: {space.name} has been booked by {request.user.username} (Faculty).\n\nDate: {d}\nTime: {st} to {et}\nPurpose: {purpose}",
                    recipients=admin_emails,
                    context_type="hall"
                )

        else:
            # === B. STUDENT BOOKING (Auto-Approved with Reference) ===
            
            # 1. Send Confirmation to Student (With Faculty Name included)
            if request.user.email:
                send_notification_email(
                    subject="Booking Confirmed",
                    message=f"Dear {request.user.username},\n\nYour booking for {space.name} on {d} is CONFIRMED.\n\nFaculty In-Charge: {faculty_name}\nTime: {st} to {et}",
                    recipients=[request.user.email],
                    context_type="hall"
                )
            
            # 2. Alert Admins (With Faculty Name included for verification)
            if admin_emails:
                send_notification_email(
                    subject=f"New Booking Alert: {space.name}",
                    message=f"ALERT: {space.name} has been booked by Student {request.user.username}.\n\nReferenced Faculty: {faculty_name}\nStatus: Auto-Approved",
                    recipients=admin_emails,
                    context_type="hall"
                )

        # In-App Notifications for Admins
        for admin in facility_admins:
            Notification.objects.create(
                user=admin,
                message=f"Alert: {request.user.username} booked {space.name}"
            )

        messages.success(request, "Booking confirmed successfully.")
        return redirect("my_bookings")

    return render(request, "booking_form.html", {"spaces": spaces, "selected_space": selected_space})

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(requested_by=request.user).order_by("-date", "-created_at")
    return render(request, "my_bookings.html", {"bookings": bookings})

@login_required
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, requested_by=request.user)
    
    if request.method == "POST" and booking.can_cancel:
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        messages.success(request, "Booking cancelled.")
        
        # Notify Admins only if a student cancels
        if not request.user.is_staff:
            admins = User.objects.filter(is_staff=True)
            for admin in admins:
                Notification.objects.create(
                    user=admin,
                    message=f"Cancelled: {request.user.username} cancelled booking for {booking.space.name}"
                )

    return redirect("my_bookings")

# ================= Admin Dashboard (Hall Booking) =================

@user_passes_test(is_admin_user)
def admin_dashboard(request):
    qs = Booking.objects.select_related("space", "requested_by")
    
    if request.GET.get("status"): qs = qs.filter(status=request.GET.get("status"))
    if request.GET.get("space_id"): qs = qs.filter(space_id=request.GET.get("space_id"))
    if request.GET.get("date"): qs = qs.filter(date=request.GET.get("date"))

    bookings = qs.order_by("-date", "start_time")
    
    today = timezone.localdate()
    stats = {
        "today_total": Booking.objects.filter(date=today).count(),
        "pending": Booking.objects.filter(status=Booking.STATUS_PENDING).count(),
        "week_approved": Booking.objects.filter(
            status=Booking.STATUS_APPROVED,
            date__gte=today - timedelta(days=today.weekday())
        ).count(),
        "blocked": BlockedDate.objects.count(),
    }

    chart_spaces = Space.objects.all()
    space_names = [s.name for s in chart_spaces]
    booking_counts = [
        Booking.objects.filter(space=s, status=Booking.STATUS_APPROVED).count()
        for s in chart_spaces
    ]

    return render(request, "admin_dashboard.html", {
        "bookings": bookings, "stats": stats, "all_spaces": chart_spaces,
        "space_names_json": json.dumps(space_names),
        "booking_counts_json": json.dumps(booking_counts),
    })

@user_passes_test(is_admin_user)
def approve_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST" and booking.status == Booking.STATUS_PENDING:
        booking.status = Booking.STATUS_APPROVED
        booking.approved_by = request.user
        booking.save()
        
        # In-App
        Notification.objects.create(
            user=booking.requested_by,
            message=f"APPROVED: Your booking for {booking.space.name} on {booking.date} is confirmed."
        )

        # Email Notification
        if booking.requested_by.email:
            send_notification_email(
                subject="Booking Approved",
                message=f"Good news! Your booking for {booking.space.name} on {booking.date} has been APPROVED.",
                recipients=[booking.requested_by.email],
                context_type="hall"
            )

        messages.success(request, "Booking approved.")
    return redirect("admin_dashboard")

@user_passes_test(is_admin_user)
def reject_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST" and booking.status == Booking.STATUS_PENDING:
        booking.status = Booking.STATUS_REJECTED
        booking.approved_by = request.user
        booking.save()
        
        # In-App
        Notification.objects.create(
            user=booking.requested_by,
            message=f"REJECTED: Your booking for {booking.space.name} on {booking.date} was declined."
        )

        # Email Notification
        if booking.requested_by.email:
            send_notification_email(
                subject="Booking Request Declined",
                message=f"We regret to inform you that your request for {booking.space.name} on {booking.date} has been REJECTED.",
                recipients=[booking.requested_by.email],
                context_type="hall"
            )

        messages.success(request, "Booking rejected.")
    return redirect("admin_dashboard")

@user_passes_test(is_admin_user)
def admin_cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST":
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        
        if booking.requested_by != request.user:
            Notification.objects.create(
                user=booking.requested_by,
                message=f"CANCELLED: Admin cancelled your booking for {booking.space.name}."
            )
        messages.success(request, "Booking cancelled.")
    return redirect("admin_dashboard")

# ================= API & Calendar =================

@require_GET
@login_required
def api_unavailable_dates(request):
    space_id = request.GET.get("space_id")
    if not space_id: return JsonResponse([], safe=False)
    
    space = get_object_or_404(Space, id=space_id)
    blocked = BlockedDate.objects.filter(
        Q(space=space) | Q(space__isnull=True), date__gte=timezone.localdate()
    ).values_list("date", flat=True)
    
    return JsonResponse([d.isoformat() for d in blocked], safe=False)

@require_GET
@login_required
def space_day_slots(request):
    space_id = request.GET.get("space_id")
    date = request.GET.get("date")
    if not (space_id and date): return JsonResponse([], safe=False)

    bookings = Booking.objects.filter(
        space_id=space_id, date=date,
        status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
    ).values("start_time", "end_time")

    return JsonResponse([
        {"start": str(b["start_time"]), "end": str(b["end_time"])} for b in bookings
    ], safe=False)

def calendar_view(request):
    return render(request, "calendar.html")

def api_bookings(request):
    bookings = Booking.objects.filter(status=Booking.STATUS_APPROVED)
    events = [{
        'title': f"{b.space.name} (Booked)",
        'start': f"{b.date.isoformat()}T{b.start_time.strftime('%H:%M:%S')}",
        'end': f"{b.date.isoformat()}T{b.end_time.strftime('%H:%M:%S')}",
        'color': '#0d6efd',
    } for b in bookings]
    return JsonResponse(events, safe=False)

# ================= Notifications =================

@login_required
def mark_notification_read(request, notif_id):
    """Marks notification read and redirects to the right page."""
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save()
    
    # === SMART REDIRECT ===
    if request.user.is_staff:
        # Check if it's a Bus Notification
        if "BUS" in notif.message or "Bus" in notif.message:
            return redirect('bus_list')
        return redirect('admin_dashboard')
    else:
        # Students: Check if Bus
        if "BUS" in notif.message or "Bus" in notif.message:
            return redirect('bus_list')
        return redirect('my_bookings')

@login_required
def notification_list(request):
    """View all notifications (read and unread)."""
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'notifications.html', {'notifications': notifications})

def logout_view(request):
    logout(request)
    return redirect("home")

# ================= BUS SYSTEM (Updated) =================

@login_required
def bus_list(request):
    is_officer = is_transport_officer(request.user)
    
    # === UPDATED LOGIC FOR TRANSPORT OFFICER ===
    if is_officer:
        # Transport Officer sees EVERYONE'S bookings
        bookings = BusBooking.objects.all().order_by('-date')
    else:
        # Regular users see ONLY their own bookings
        bookings = BusBooking.objects.filter(requested_by=request.user).order_by('-date')
    
    buses = Bus.objects.all()
    
    # We pass 'is_transport_officer' to template so we can show/hide buttons
    return render(request, "bus_list.html", {
        "bookings": bookings, 
        "buses": buses,
        "is_transport_officer": is_officer
    })

@login_required
def book_bus(request):
    buses = Bus.objects.all()
    if request.method == "POST":
        bus_id = request.POST.get("bus_id")
        date_str = request.POST.get("date")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        origin = request.POST.get("origin")
        destination = request.POST.get("destination")
        purpose = request.POST.get("purpose")
        
        # Simple Validation
        if not all([bus_id, date_str, start_time, end_time, origin, destination]):
            messages.error(request, "Please fill all fields")
            return redirect("book_bus")
            
        BusBooking.objects.create(
            bus_id=bus_id,
            requested_by=request.user,
            date=date_str,
            start_time=start_time,
            end_time=end_time,
            origin=origin,
            destination=destination,
            purpose=purpose,
            status='Pending' # Buses always pending for Transport Admin
        )
        
        # Notify Admin (Transport Officer)
        officers = User.objects.filter(groups__name='Transport')
        officer_emails = [u.email for u in officers if u.email]

        # 1. Email to Transport Officers
        send_notification_email(
            subject=f"New Bus Request: {origin} to {destination}",
            message=f"User {request.user.username} requested a bus on {date_str}.\nRoute: {origin} -> {destination}\nPurpose: {purpose}",
            recipients=officer_emails,
            context_type="bus"  # <--- Triggers "Rajagiri Transport Officer" sender name
        )

        # 2. Confirmation Email to Student
        if request.user.email:
            send_notification_email(
                subject="Bus Request Received",
                message=f"Dear {request.user.username},\n\nYour bus request for {date_str} ({origin} to {destination}) has been received.",
                recipients=[request.user.email],
                context_type="bus"
            )

        # In-App Notification
        for officer in officers:
            Notification.objects.create(
                user=officer, 
                message=f"New BUS Request: {request.user.username} from {origin} to {destination} on {date_str}"
            )
            
        messages.success(request, "Bus request submitted to Transport Officer.")
        return redirect("bus_list")
        
    return render(request, "book_bus.html", {"buses": buses})

# === NEW: TRANSPORT OFFICER ACTIONS ===

@user_passes_test(is_transport_officer)
def approve_bus_booking(request, booking_id):
    booking = get_object_or_404(BusBooking, id=booking_id)
    if request.method == "POST":
        booking.status = 'Approved'
        booking.save()
        
        Notification.objects.create(
            user=booking.requested_by,
            message=f"BUS APPROVED: Your trip to {booking.destination} is confirmed."
        )

        # Email Notification
        if booking.requested_by.email:
            send_notification_email(
                subject="Bus Booking Approved",
                message=f"Your bus trip to {booking.destination} on {booking.date} has been confirmed.",
                recipients=[booking.requested_by.email],
                context_type="bus"
            )

        messages.success(request, "Bus booking approved.")
    return redirect("bus_list")

@user_passes_test(is_transport_officer)
def reject_bus_booking(request, booking_id):
    booking = get_object_or_404(BusBooking, id=booking_id)
    if request.method == "POST":
        booking.status = 'Rejected'
        booking.save()
        
        Notification.objects.create(
            user=booking.requested_by,
            message=f"BUS REJECTED: Your trip to {booking.destination} was declined."
        )

        # Email Notification
        if booking.requested_by.email:
            send_notification_email(
                subject="Bus Booking Rejected",
                message=f"Your bus trip to {booking.destination} on {booking.date} was unavailable.",
                recipients=[booking.requested_by.email],
                context_type="bus"
            )

        messages.success(request, "Bus booking rejected.")
    return redirect("bus_list")

# ================= TIMETABLE AUTOMATION (Crash Fixed) =================

@user_passes_test(is_admin_user)
def upload_timetable(request):
    spaces = Space.objects.all()
    
    if request.method == "POST":
        space_id = request.POST.get("space_id")
        day_of_week = int(request.POST.get("day_of_week"))
        
        # === 1. Extract Student Count (FIXED CRASH HERE) ===
        expected_count = request.POST.get("expected_count") or 0
        
        # === 2. Check Time Inputs ===
        start_custom = request.POST.get("start_time_custom")
        end_custom = request.POST.get("end_time_custom")
        
        if start_custom and end_custom:
            start_time = start_custom
            end_time = end_custom
        else:
            start_time = request.POST.get("start_time_select")
            end_time = request.POST.get("end_time_select")

        sem_start = parse_date(request.POST.get("sem_start"))
        sem_end = parse_date(request.POST.get("sem_end"))
        subject = request.POST.get("subject")

        space = get_object_or_404(Space, id=space_id)
        
        current_date = sem_start
        booking_count = 0
        
        while current_date <= sem_end:
            if current_date.weekday() == day_of_week:
                conflict = Booking.objects.filter(
                    space=space, date=current_date,
                    status=Booking.STATUS_APPROVED
                ).filter(Q(start_time__lt=end_time, end_time__gt=start_time)).exists()
                
                if not conflict:
                    Booking.objects.create(
                        space=space,
                        requested_by=request.user,
                        date=current_date,
                        start_time=start_time,
                        end_time=end_time,
                        purpose=f"TIMETABLE: {subject}",
                        status=Booking.STATUS_APPROVED,
                        approved_by=request.user,
                        expected_count=expected_count
                    )
                    booking_count += 1
            
            current_date += timedelta(days=1)
            
        messages.success(request, f"Success! Generated {booking_count} bookings for {subject}.")
        return redirect("admin_dashboard")

    return render(request, "upload_timetable.html", {"spaces": spaces})

def login_view(request):
    """Custom login view to handle student/staff login."""
    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # === SMART LOGIN REDIRECT ===
            if is_transport_officer(user):
                return redirect('bus_list')
            
            if 'next' in request.POST:
                return redirect(request.POST.get('next'))
            
            return redirect("home")
    else:
        form = AuthenticationForm()
    
    return render(request, "login.html", {"form": form})