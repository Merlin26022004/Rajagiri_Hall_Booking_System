from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_GET

from .auth_utils import authenticate_user, login_user, logout_user, get_current_user
from .decorators import custom_login_required, role_required
from .utils import create_notification, notify_admins, log_action
from .models import Hall, Booking, BlockedDate, CustomUser, AuditLog

# ============================================================
# Auth Views
# ============================================================

def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        
        user = authenticate_user(email, password)
        if user:
            login_user(request, user)
            log_action(user, "User logged in")
            messages.success(request, f"Welcome back, {user.full_name}!")
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            
            if user.role in [CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN]:
                return redirect('admin_dashboard')
            return redirect('my_bookings')
        else:
            messages.error(request, "Invalid credentials.")
    
    return render(request, "login.html")


def logout_view(request):
    user = get_current_user(request)
    if user:
        log_action(user, "User logged out")
    logout_user(request)
    messages.info(request, "You have been logged out.")
    return redirect("home")


# ============================================================
# Public / Home / Halls
# ============================================================

def home(request):
    """Homepage with hero + snapshot stats + a few halls."""
    halls = Hall.objects.filter(is_active=True)[:6]

    today = timezone.localdate()
    # Fix: Count bookings for today (logic remains similar)
    today_total = Booking.objects.filter(date=today).count()
    pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()

    stats = {
        "today_total": today_total,
        "pending": pending,
    }

    return render(
        request,
        "index.html",
        {
            "halls": halls,
            "stats": stats,
            "user": get_current_user(request) # Context processor for user is removed, pass manually
        },
    )


def hall_list(request):
    """List all active halls."""
    halls = Hall.objects.filter(is_active=True)
    return render(request, "hall_list.html", {"halls": halls, "user": get_current_user(request)})


def hall_detail(request, hall_id):
    """Show detailed info for a hall."""
    hall = get_object_or_404(Hall, pk=hall_id)
    return render(request, "hall_detail.html", {"hall": hall, "user": get_current_user(request)})


# ============================================================
# Booking: create, list, cancel
# ============================================================

@custom_login_required
def book_hall(request, hall_id):
    """Create a new booking request for a specific hall."""
    hall = get_object_or_404(Hall, pk=hall_id)
    current_user = get_current_user(request)

    if request.method == "POST":
        date_str = request.POST.get("date")
        start_time_str = request.POST.get("start_time")
        end_time_str = request.POST.get("end_time")
        expected_count = request.POST.get("expected_count")
        purpose = request.POST.get("purpose")

        # Basic validation
        if not all([date_str, start_time_str, end_time_str, expected_count, purpose]):
            messages.error(request, "Please fill all required fields.")
            return redirect("hall_detail", hall_id=hall.id)

        # Capacity check
        try:
            expected_count_int = int(expected_count)
        except ValueError:
            messages.error(request, "Expected count must be a number.")
            return redirect("hall_detail", hall_id=hall.id)

        if expected_count_int > hall.seating_capacity:
            messages.error(request, f"Expected count exceeds hall capacity ({hall.seating_capacity}).")
            return redirect("hall_detail", hall_id=hall.id)

        # Parse date & time
        d = parse_date(date_str)
        st = parse_time(start_time_str)
        et = parse_time(end_time_str)

        if not (d and st and et):
            messages.error(request, "Invalid date or time.")
            return redirect("hall_detail", hall_id=hall.id)

        if et <= st:
            messages.error(request, "End time must be after start time.")
            return redirect("hall_detail", hall_id=hall.id)

        # Blocked date check
        if BlockedDate.objects.filter(
            Q(hall=hall) | Q(hall__isnull=True),
            date=d,
        ).exists():
            messages.error(request, "This date is blocked for this hall.")
            return redirect("hall_detail", hall_id=hall.id)

        # Overlapping booking check
        conflict = (
            Booking.objects.filter(
                hall=hall,
                date=d,
                status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
            )
            .filter(Q(start_time__lt=et, end_time__gt=st))
            .exists()
        )

        if conflict:
            messages.error(request, "Time slot conflicts with an existing booking.")
            return redirect("hall_detail", hall_id=hall.id)

        # Create booking
        Booking.objects.create(
            hall=hall,
            requested_by=current_user,
            date=d,
            start_time=st,
            end_time=et,
            expected_count=expected_count_int,
            purpose=purpose,
        )

        messages.success(request, "Booking request submitted for approval.")
        notify_admins(f"New booking request from {current_user.full_name} for {hall.name} on {d}")
        log_action(current_user, f"Submitted booking request for {hall.name} on {d}")
        return redirect("my_bookings")
    
    # GET request redirects to detail page as form is likely embedded or modal there, 
    # but strictly speaking logic belongs there. For now redirect back.
    return redirect("hall_detail", hall_id=hall_id)


@custom_login_required
def my_bookings(request):
    """List bookings for the logged-in user."""
    current_user = get_current_user(request)
    bookings = (
        Booking.objects.filter(requested_by=current_user)
        .select_related("hall", "approved_by")
        .order_by("-date", "-created_at")
    )

    return render(
        request,
        "my_bookings.html",
        {
            "bookings": bookings,
            "user": current_user,
        },
    )


@custom_login_required
def cancel_booking(request, booking_id):
    """User cancels their own booking (if still allowed)."""
    current_user = get_current_user(request)
    booking = get_object_or_404(Booking, id=booking_id, requested_by=current_user)

    if request.method != "POST":
        raise Http404()

    if not booking.can_cancel:
        messages.error(request, "You cannot cancel this booking.")
        return redirect("my_bookings")

    booking.status = Booking.STATUS_CANCELLED
    booking.cancellation_reason = request.POST.get("reason", "")
    booking.save()
    booking.save()
    messages.success(request, "Booking cancelled.")
    notify_admins(f"Booking cancelled by {current_user.full_name} for {booking.hall.name} on {booking.date}. Reason: {request.POST.get('reason', '')}")
    log_action(current_user, f"Cancelled booking {booking.id} for {booking.hall.name}")
    return redirect("my_bookings")


# ============================================================
# Admin / Receptionist Dashboard
# ============================================================

@role_required([CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN])
def admin_dashboard(request):
    """Dashboard for managing bookings."""
    qs = Booking.objects.select_related("hall", "requested_by", "approved_by")

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    hall_id = request.GET.get("hall_id")
    if hall_id:
        qs = qs.filter(hall_id=hall_id)

    date = request.GET.get("date")
    if date:
        qs = qs.filter(date=date)

    bookings = qs.order_by("-date", "start_time")

    today = timezone.localdate()
    today_total = Booking.objects.filter(date=today).count()
    pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()
    
    stats = {
        "today_total": today_total,
        "pending": pending,
    }

    all_halls = Hall.objects.all()

    return render(
        request,
        "admin_dashboard.html",
        {
            "bookings": bookings,
            "stats": stats,
            "all_halls": all_halls,
            "user": get_current_user(request),
        },
    )


@role_required([CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN])
def approve_booking(request, booking_id):
    if request.method != "POST":
        raise Http404()
    
    booking = get_object_or_404(Booking, id=booking_id)
    current_user = get_current_user(request)

    if booking.status != Booking.STATUS_PENDING:
        messages.error(request, "Only pending bookings can be approved.")
        return redirect("admin_dashboard")

    booking.status = Booking.STATUS_APPROVED
    booking.approved_by = current_user
    booking.save()
    booking.save()
    messages.success(request, "Booking approved.")
    create_notification(booking.requested_by, f"Your booking for {booking.hall.name} on {booking.date} has been APPROVED.")
    log_action(current_user, f"Approved booking {booking.id} for {booking.requested_by.full_name}")
    return redirect("admin_dashboard")


@role_required([CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN])
def reject_booking(request, booking_id):
    if request.method != "POST":
        raise Http404()

    booking = get_object_or_404(Booking, id=booking_id)
    current_user = get_current_user(request)

    if booking.status != Booking.STATUS_PENDING:
        messages.error(request, "Only pending bookings can be rejected.")
        return redirect("admin_dashboard")

    booking.status = Booking.STATUS_REJECTED
    booking.rejection_reason = request.POST.get("reason", "")
    booking.approved_by = current_user
    booking.save()
    booking.save()
    messages.success(request, "Booking rejected.")
    create_notification(booking.requested_by, f"Your booking for {booking.hall.name} on {booking.date} has been REJECTED. Reason: {request.POST.get('reason', '')}")
    log_action(current_user, f"Rejected booking {booking.id} for {booking.requested_by.full_name}")
    return redirect("admin_dashboard")


# ============================================================
# API Endpoints (Helpers for JS)
# ============================================================

@require_GET
@custom_login_required
def api_unavailable_dates(request):
    hall_id = request.GET.get("hall_id")
    if not hall_id:
        return JsonResponse([], safe=False)

    hall = get_object_or_404(Hall, id=hall_id)
    today = timezone.localdate()

    blocked = BlockedDate.objects.filter(
        Q(hall=hall) | Q(hall__isnull=True),
        date__gte=today,
    ).values_list("date", flat=True)

    result = [d.isoformat() for d in blocked]
    return JsonResponse(result, safe=False)

@role_required([CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN])
def reschedule_booking(request, booking_id):
    """Reschedule a booking to a new date/time."""
    if request.method != "POST":
        raise Http404()

    booking = get_object_or_404(Booking, id=booking_id)
    current_user = get_current_user(request)

    date_str = request.POST.get("date")
    start_time_str = request.POST.get("start_time")
    end_time_str = request.POST.get("end_time")

    if not all([date_str, start_time_str, end_time_str]):
        messages.error(request, "All fields are required for rescheduling.")
        return redirect("admin_dashboard")

    d = parse_date(date_str)
    st = parse_time(start_time_str)
    et = parse_time(end_time_str)

    if not (d and st and et):
        messages.error(request, "Invalid date or time.")
        return redirect("admin_dashboard")

    if et <= st:
        messages.error(request, "End time must be after start time.")
        return redirect("admin_dashboard")

    # Conflict check (exclude current booking)
    conflict = (
        Booking.objects.filter(
            hall=booking.hall,
            date=d,
            status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED],
        )
        .exclude(id=booking.id)
        .filter(Q(start_time__lt=et, end_time__gt=st))
        .exists()
    )

    if conflict:
        messages.error(request, "The new slot conflicts with an existing booking.")
        return redirect("admin_dashboard")

    # Update booking
    booking.date = d
    booking.start_time = st
    booking.end_time = et
    # Note: Status usually remains approved or pending depending on workflow. 
    # If admin does it, we assume it's approved.
    if booking.status == Booking.STATUS_REJECTED:
         booking.status = Booking.STATUS_APPROVED
         booking.approved_by = current_user
    
    booking.save()
    messages.success(request, "Booking rescheduled successfully.")
    log_action(current_user, f"Rescheduled booking {booking_id} to {d} {st}-{et}")
    create_notification(booking.requested_by, f"Your booking for {booking.hall.name} on {booking.date} has been RESCHEDULED to {d} {st}-{et}.")
    return redirect("admin_dashboard")

@role_required([CustomUser.SUPER_ADMIN])
def manage_users(request):
    """View to list and manage users."""
    users = CustomUser.objects.all().order_by("role", "full_name")
    return render(request, "manage_users.html", {"users": users})

@role_required([CustomUser.SUPER_ADMIN])
def toggle_user_status(request, user_id):
    """Toggle user active status."""
    if request.method != "POST":
        raise Http404()
    
    user = get_object_or_404(CustomUser, id=user_id)
    
    # Prevent deactivating self
    current_user_id = request.session.get('user_id')
    if user.id == current_user_id:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("manage_users")
        
    user.is_active = not user.is_active
    user.save()
    
    status = "activated" if user.is_active else "deactivated"
    messages.success(request, f"User {user.full_name} has been {status}.")
    current_admin = get_current_user(request)
    log_action(current_admin, f"Toggled status for user {user.full_name} to {status}")
    return redirect("manage_users")

@role_required([CustomUser.SUPER_ADMIN])
def view_audit_log(request):
    """View system audit logs."""
    logs = AuditLog.objects.select_related("user").all()[:200]
    return render(request, "audit_log.html", {"logs": logs})

@role_required([CustomUser.RECEPTIONIST, CustomUser.SUPER_ADMIN])
def manage_blocked_dates(request):
    """View to manage blocked dates."""
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "add":
            date_str = request.POST.get("date")
            hall_id = request.POST.get("hall_id")
            reason = request.POST.get("reason")
            
            if not date_str:
                messages.error(request, "Date is required.")
            else:
                d = parse_date(date_str)
                hall = None
                if hall_id:
                    hall = get_object_or_404(Hall, id=hall_id)
                
                # Check duplication
                if BlockedDate.objects.filter(hall=hall, date=d).exists():
                    messages.error(request, "This date is already blocked for this hall/all halls.")
                else:
                    BlockedDate.objects.create(hall=hall, date=d, reason=reason)
                    messages.success(request, "Date blocked successfully.")
                    log_action(get_current_user(request), f"Blocked date {d} for {hall.name if hall else 'All Halls'}")
                    
        elif action == "delete":
            block_id = request.POST.get("block_id")
            block = get_object_or_404(BlockedDate, id=block_id)
            d = block.date
            h_name = block.hall.name if block.hall else "All Halls"
            block.delete()
            messages.success(request, "Block removed.")
            log_action(get_current_user(request), f"Unblocked date {d} for {h_name}")
            
        return redirect("manage_blocked_dates")

    blocked_dates = BlockedDate.objects.select_related("hall").all().order_by("-date")
    halls = Hall.objects.filter(is_active=True)
    return render(request, "blocked_dates.html", {"blocked_dates": blocked_dates, "halls": halls})
