import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_GET

from .models import Space, Booking, BlockedDate, Notification

# ================= Helpers =================

def is_admin_user(user):
    """Who can see the custom admin dashboard & approve bookings."""
    return user.is_staff or user.is_superuser

# ================= Public / Home / Spaces =================

def home(request):
    spaces = Space.objects.all()[:6]
    today = timezone.localdate()
    
    # Simple stats for hero section
    stats = {
        "today_total": Booking.objects.filter(date=today).count(),
        "pending": Booking.objects.filter(status=Booking.STATUS_PENDING).count(),
        "week_approved": Booking.objects.filter(
            status=Booking.STATUS_APPROVED,
            date__range=[today, today + timedelta(days=6)]
        ).count(),
        "blocked": BlockedDate.objects.filter(date__gte=today).count(),
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
        # Extract data
        space_id = request.POST.get("space_id")
        date_str = request.POST.get("date")
        start_time_str = request.POST.get("start_time")
        end_time_str = request.POST.get("end_time")
        expected_count = request.POST.get("expected_count")
        purpose = request.POST.get("purpose")

        if not all([space_id, date_str, start_time_str, end_time_str, expected_count, purpose]):
            messages.error(request, "Please fill all required fields.")
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

        if not (d and st and et) or et <= st:
            messages.error(request, "Invalid date or time range.")
            return redirect("book_space")

        # Validation: Blocked Dates & Conflicts
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

        # Create Booking
        Booking.objects.create(
            space=space, requested_by=request.user, date=d,
            start_time=st, end_time=et,
            expected_count=expected_count_int, purpose=purpose,
        )

        # NOTIFICATION: Alert all admins
        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                message=f"New Request: {request.user.username} wants {space.name} on {d}"
            )

        messages.success(request, "Booking request submitted.")
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
        
        # Notify Admins of cancellation
        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                message=f"Cancelled: {request.user.username} cancelled booking for {booking.space.name}"
            )

    return redirect("my_bookings")

# ================= Admin Dashboard =================

@user_passes_test(is_admin_user)
def admin_dashboard(request):
    qs = Booking.objects.select_related("space", "requested_by")
    
    # Filter Logic
    if request.GET.get("status"): qs = qs.filter(status=request.GET.get("status"))
    if request.GET.get("space_id"): qs = qs.filter(space_id=request.GET.get("space_id"))
    if request.GET.get("date"): qs = qs.filter(date=request.GET.get("date"))

    bookings = qs.order_by("-date", "start_time")
    
    # Statistics
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

    # Chart Data
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
        
        # NOTIFICATION: Alert Student
        Notification.objects.create(
            user=booking.requested_by,
            message=f"APPROVED: Your booking for {booking.space.name} on {booking.date} is confirmed."
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
        
        # NOTIFICATION: Alert Student
        Notification.objects.create(
            user=booking.requested_by,
            message=f"REJECTED: Your booking for {booking.space.name} on {booking.date} was declined."
        )
        messages.success(request, "Booking rejected.")
    return redirect("admin_dashboard")

@user_passes_test(is_admin_user)
def admin_cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST":
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        
        # NOTIFICATION: Alert Student
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
    """Marks a notification as read and stays on the same page."""
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save()
    return redirect(request.META.get('HTTP_REFERER', 'home'))

def logout_view(request):
    logout(request)
    return redirect("home")