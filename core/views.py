import json  
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_GET

from .models import Space, Booking, BlockedDate


# ============================================================
# Helpers
# ============================================================

def is_admin_user(user):
    """Who can see the custom admin dashboard & approve bookings."""
    return user.is_staff or user.is_superuser


# ============================================================
# Public / Home / Spaces
# ============================================================

def home(request):
    """Homepage with hero + snapshot stats + a few spaces."""
    spaces = Space.objects.all()[:6]

    today = timezone.localdate()
    today_total = Booking.objects.filter(date=today).count()
    pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()

    week_start = today - timedelta(days=today.weekday())
    week_approved = Booking.objects.filter(
        status=Booking.STATUS_APPROVED,
        date__gte=week_start,
        date__lte=week_start + timedelta(days=6),
    ).count()

    blocked = BlockedDate.objects.filter(date__gte=today).count()

    stats = {
        "today_total": today_total,
        "pending": pending,
        "week_approved": week_approved,
        "blocked": blocked,
    }

    return render(
        request,
        "index.html",
        {
            "spaces": spaces,
            "stats": stats,
        },
    )


def space_list(request):
    """List all bookable spaces."""
    spaces = Space.objects.all()
    return render(request, "spaces.html", {"spaces": spaces})


def space_availability(request, space_id):
    """Show upcoming bookings + blocked dates for one space."""
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

    return render(
        request,
        "space_availability.html",
        {
            "space": space,
            "bookings": bookings,
            "blocked_dates": blocked_dates,
        },
    )


# ============================================================
# Booking: create, list, cancel
# ============================================================

@login_required
def book_space(request):
    """Create a new booking request."""
    spaces = Space.objects.all()
    selected_space_id = request.GET.get("space_id")
    selected_space = None

    if selected_space_id:
        try:
            selected_space = Space.objects.get(id=selected_space_id)
        except Space.DoesNotExist:
            selected_space = None

    if request.method == "POST":
        space_id = request.POST.get("space_id")
        date_str = request.POST.get("date")
        start_time_str = request.POST.get("start_time")
        end_time_str = request.POST.get("end_time")
        expected_count = request.POST.get("expected_count")
        purpose = request.POST.get("purpose")

        # Basic validation
        if not all([space_id, date_str, start_time_str, end_time_str, expected_count, purpose]):
            messages.error(request, "Please fill all required fields.")
            return redirect("book_space")

        space = get_object_or_404(Space, id=space_id)

        # Capacity check
        try:
            expected_count_int = int(expected_count)
        except ValueError:
            messages.error(request, "Expected count must be a number.")
            return redirect("book_space")

        if expected_count_int > space.capacity:
            messages.error(request, "Expected count exceeds space capacity.")
            return redirect("book_space")

        # Parse date & time
        d = parse_date(date_str)
        st = parse_time(start_time_str)
        et = parse_time(end_time_str)

        if not (d and st and et):
            messages.error(request, "Invalid date or time.")
            return redirect("book_space")

        if et <= st:
            messages.error(request, "End time must be after start time.")
            return redirect("book_space")

        # Blocked date check (blocks full day)
        if BlockedDate.objects.filter(
            Q(space=space) | Q(space__isnull=True),
            date=d,
        ).exists():
            messages.error(request, "This date is blocked for this space.")
            return redirect("book_space")

        # Overlapping booking check (time-based)
        conflict = (
            Booking.objects.filter(
                space=space,
                date=d,
                status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
            )
            .filter(Q(start_time__lt=et, end_time__gt=st))
            .exists()
        )

        if conflict:
            messages.error(request, "Time slot conflicts with an existing booking.")
            return redirect("book_space")

        # Create booking
        Booking.objects.create(
            space=space,
            requested_by=request.user,
            date=d,
            start_time=st,
            end_time=et,
            expected_count=expected_count_int,
            purpose=purpose,
        )

        messages.success(request, "Booking request submitted for approval.")
        return redirect("my_bookings")

    return render(
        request,
        "booking_form.html",
        {
            "spaces": spaces,
            "selected_space": selected_space,
        },
    )


@login_required
def my_bookings(request):
    """List bookings for the logged-in user."""
    bookings = (
        Booking.objects.filter(requested_by=request.user)
        .select_related("space", "approved_by")
        .order_by("-date", "-created_at")
    )

    return render(
        request,
        "my_bookings.html",
        {
            "bookings": bookings,
        },
    )


@login_required
def cancel_booking(request, booking_id):
    """User cancels their own booking (if still allowed)."""
    booking = get_object_or_404(Booking, id=booking_id, requested_by=request.user)

    if request.method != "POST":
        raise Http404()

    if not booking.can_cancel:
        messages.error(request, "You cannot cancel this booking.")
        return redirect("my_bookings")

    booking.status = Booking.STATUS_CANCELLED
    booking.save()
    messages.success(request, "Booking cancelled.")
    return redirect("my_bookings")


# ============================================================
# Custom Admin Dashboard + Actions
# ============================================================

@user_passes_test(is_admin_user)
def admin_dashboard(request):
    """Custom dashboard for staff/superusers to manage bookings."""
    qs = Booking.objects.select_related("space", "requested_by", "approved_by")

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    space_id = request.GET.get("space_id")
    if space_id:
        qs = qs.filter(space_id=space_id)

    date = request.GET.get("date")
    if date:
        qs = qs.filter(date=date)

    bookings = qs.order_by("-date", "start_time")

    today = timezone.localdate()
    today_total = Booking.objects.filter(date=today).count()
    pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()
    week_start = today - timedelta(days=today.weekday())
    week_approved = Booking.objects.filter(
        status=Booking.STATUS_APPROVED,
        date__gte=week_start,
        date__lte=week_start + timedelta(days=6),
    ).count()
    blocked = BlockedDate.objects.count()

    stats = {
        "today_total": today_total,
        "pending": pending,
        "week_approved": week_approved,
        "blocked": blocked,
    }

    all_spaces = Space.objects.all()

    # --- NEW: Chart Data Calculation ---
    # Prepare data for "Most Booked Spaces" chart
    chart_spaces = Space.objects.all()
    space_names = [s.name for s in chart_spaces]
    booking_counts = []
    
    for s in chart_spaces:
        # Count only APPROVED bookings for accurate popularity stats
        count = Booking.objects.filter(space=s, status=Booking.STATUS_APPROVED).count()
        booking_counts.append(count)

    return render(
        request,
        "admin_dashboard.html",
        {
            "bookings": bookings,
            "stats": stats,
            "all_spaces": all_spaces,
            # Send JSON strings for Chart.js
            "space_names_json": json.dumps(space_names),
            "booking_counts_json": json.dumps(booking_counts),
        },
    )


@user_passes_test(is_admin_user)
def approve_booking(request, booking_id):
    if request.method != "POST":
        raise Http404()

    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status != Booking.STATUS_PENDING:
        messages.error(request, "Only pending bookings can be approved.")
        return redirect("admin_dashboard")

    booking.status = Booking.STATUS_APPROVED
    booking.approved_by = request.user
    booking.save()
    messages.success(request, "Booking approved.")
    return redirect("admin_dashboard")


@user_passes_test(is_admin_user)
def reject_booking(request, booking_id):
    if request.method != "POST":
        raise Http404()

    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status != Booking.STATUS_PENDING:
        messages.error(request, "Only pending bookings can be rejected.")
        return redirect("admin_dashboard")

    booking.status = Booking.STATUS_REJECTED
    booking.approved_by = request.user
    booking.save()
    messages.success(request, "Booking rejected.")
    return redirect("admin_dashboard")


@user_passes_test(is_admin_user)
def admin_cancel_booking(request, booking_id):
    if request.method != "POST":
        raise Http404()

    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status not in [Booking.STATUS_APPROVED, Booking.STATUS_PENDING]:
        messages.error(request, "Only pending/approved bookings can be cancelled.")
        return redirect("admin_dashboard")

    booking.status = Booking.STATUS_CANCELLED
    booking.save()
    messages.success(request, "Booking cancelled.")
    return redirect("admin_dashboard")


# ============================================================
# API Endpoints
# ============================================================

@require_GET
@login_required
def api_unavailable_dates(request):
    """
    Return dates that are fully blocked for a space.
    """
    space_id = request.GET.get("space_id")
    if not space_id:
        return JsonResponse([], safe=False)

    space = get_object_or_404(Space, id=space_id)
    today = timezone.localdate()

    blocked = BlockedDate.objects.filter(
        Q(space=space) | Q(space__isnull=True),
        date__gte=today,
    ).values_list("date", flat=True)

    result = [d.isoformat() for d in blocked]
    return JsonResponse(result, safe=False)


@require_GET
@login_required
def space_day_slots(request):
    """
    Return time slots already booked for a given space on a given date.
    """
    space_id = request.GET.get("space_id")
    date = request.GET.get("date")
    if not (space_id and date):
        return JsonResponse([], safe=False)

    bookings = Booking.objects.filter(
        space_id=space_id,
        date=date,
        status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
    ).values("start_time", "end_time")

    data = [
        {"start": str(b["start_time"]), "end": str(b["end_time"])}
        for b in bookings
    ]
    return JsonResponse(data, safe=False)


# ============================================================
# NEW: Calendar & Visualization Features
# ============================================================

def calendar_view(request):
    """Render the full-page availability calendar."""
    return render(request, "calendar.html")

def api_bookings(request):
    """
    Return JSON events for FullCalendar.
    Only returns APPROVED bookings to show confirmed busy slots.
    """
    # Fetch approved bookings
    bookings = Booking.objects.filter(status=Booking.STATUS_APPROVED)
    
    events = []
    for b in bookings:
        # FullCalendar expects 'start' and 'end' in ISO format (YYYY-MM-DDTHH:MM:SS)
        start_dt = f"{b.date.isoformat()}T{b.start_time.strftime('%H:%M:%S')}"
        end_dt = f"{b.date.isoformat()}T{b.end_time.strftime('%H:%M:%S')}"
        
        events.append({
            'title': f"{b.space.name} (Booked)",
            'start': start_dt,
            'end': end_dt,
            'color': '#dc3545', # Bootstrap 'danger' red
        })
    
    return JsonResponse(events, safe=False)


# ============================================================
# Auth helpers
# ============================================================

def logout_view(request):
    """Logout and go back to home."""
    logout(request)
    return redirect("home")