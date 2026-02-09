import json
from datetime import timedelta, date
from django.contrib import messages
from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib.auth.models import User, Group
from django.db.models import Q, ProtectedError # Added ProtectedError
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.core.paginator import Paginator 
from django.conf import settings

# === IMPORTS ===
from .models import Space, Booking, BlockedDate, Notification, Bus, BusBooking, Facility, SpaceType
from .decorators import approval_required
from .forms import SpaceForm, FacilityForm, SpaceTypeForm

# ================= Helpers =================

def is_dashboard_authorized(user):
    """
    Access Control for Admin Dashboard.
    Allows access to:
    1. Superusers
    2. Users in 'Faculty' or 'Admin' groups
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['Faculty', 'Admin']).exists()

def is_transport_officer(user):
    """Check if user belongs to the 'Transport' group."""
    return user.groups.filter(name='Transport').exists()

def send_notification_email(subject, message, recipients, context_type="hall"):
    """
    Sends email with dynamic sender name based on context.
    """
    if not recipients:
        return

    sender_email = settings.EMAIL_HOST_USER
    if context_type == "hall":
        from_email = f"Rajagiri Facility Management <{sender_email}>"
    elif context_type == "bus":
        from_email = f"Rajagiri Transport Officer <{sender_email}>"
    else:
        from_email = sender_email

    try:
        send_mail(
            subject, message, from_email, recipients, fail_silently=True
        )
    except Exception as e:
        print(f"Email Error: {e}")

# ================= Public / Home / Spaces =================

def home(request):
    """Homepage with hero + personalized snapshot stats."""
    
    # If Transport Officer logs in, send them straight to Bus Dashboard.
    if request.user.is_authenticated and is_transport_officer(request.user):
        return redirect('bus_list')

    spaces = Space.objects.all()[:6]
    today = timezone.localdate()
    
    today_total = 0
    pending = 0
    week_approved = 0
    blocked = BlockedDate.objects.filter(date__gte=today).count()

    if request.user.is_authenticated:
        if request.user.is_staff or is_dashboard_authorized(request.user):
            # ADMIN VIEW
            today_total = Booking.objects.filter(date=today).count()
            pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()
            week_approved = Booking.objects.filter(
                status=Booking.STATUS_APPROVED,
                date__range=[today, today + timedelta(days=6)]
            ).count()
        else:
            # STUDENT VIEW
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
@approval_required
def book_space(request):
    spaces = Space.objects.all()
    facilities = Facility.objects.all()
    
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
        faculty_name = request.POST.get("faculty_in_charge")
        selected_facility_ids = request.POST.getlist("facilities")

        if not all([space_id, date_str, start_time_str, end_time_str, expected_count, purpose]):
            messages.error(request, "Please fill all required fields.")
            return redirect("book_space")

        if not request.user.is_staff and not faculty_name:
            messages.error(request, "Students must specify the Faculty In-Charge.")
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

        # Auto-Approve Logic
        booking_status = Booking.STATUS_APPROVED
        approver = request.user if request.user.is_staff else None

        booking = Booking.objects.create(
            space=space, requested_by=request.user, date=d,
            start_time=st, end_time=et,
            expected_count=expected_count_int, purpose=purpose,
            status=booking_status, approved_by=approver,
            faculty_in_charge=faculty_name
        )
        
        if selected_facility_ids:
            booking.requested_facilities.set(selected_facility_ids)

        # Notifications
        facility_admins = User.objects.filter(is_superuser=True).exclude(id=request.user.id)
        admin_emails = [u.email for u in facility_admins if u.email]
        
        facility_msg = ""
        if selected_facility_ids:
            names = [f.name for f in Facility.objects.filter(id__in=selected_facility_ids)]
            facility_msg = "\nFacilities Requested: " + ", ".join(names)

        if request.user.is_staff:
            if request.user.email:
                send_notification_email(
                    subject="Booking Confirmed",
                    message=f"Dear {request.user.username},\n\nConfirmed for {space.name} on {d}.\nPurpose: {purpose}{facility_msg}",
                    recipients=[request.user.email],
                    context_type="hall"
                )
            if admin_emails:
                send_notification_email(
                    subject=f"New Booking Alert: {space.name}",
                    message=f"ALERT: {space.name} booked by {request.user.username} (Faculty).{facility_msg}",
                    recipients=admin_emails,
                    context_type="hall"
                )
        else:
            if request.user.email:
                send_notification_email(
                    subject="Booking Confirmed",
                    message=f"Dear {request.user.username},\n\nConfirmed for {space.name} on {d}.\nFaculty Ref: {faculty_name}{facility_msg}",
                    recipients=[request.user.email],
                    context_type="hall"
                )
            if admin_emails:
                send_notification_email(
                    subject=f"New Booking Alert: {space.name}",
                    message=f"ALERT: {space.name} booked by Student {request.user.username}.\nFaculty Ref: {faculty_name}{facility_msg}",
                    recipients=admin_emails,
                    context_type="hall"
                )

        for admin in facility_admins:
            Notification.objects.create(
                user=admin,
                message=f"Alert: {request.user.username} booked {space.name}"
            )

        messages.success(request, "Booking confirmed successfully.")
        return redirect("my_bookings")

    return render(request, "booking_form.html", {
        "spaces": spaces, 
        "selected_space": selected_space,
        "facilities": facilities
    })

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
        
        facility_admins = User.objects.filter(is_superuser=True)
        admin_emails = [u.email for u in facility_admins if u.email]
        
        send_notification_email(
            subject=f"Cancelled: {booking.space.name} on {booking.date}",
            message=f"FYI: {request.user.username} has CANCELLED their booking.",
            recipients=admin_emails,
            context_type="hall"
        )

        for admin in facility_admins:
            Notification.objects.create(
                user=admin,
                message=f"Cancelled: {request.user.username} cancelled booking for {booking.space.name}"
            )

    return redirect("my_bookings")

# ================= Admin Dashboard (OPERATIONAL) =================

@user_passes_test(is_dashboard_authorized)
def admin_dashboard(request):
    """
    Operational Dashboard: Shows only ACTIONABLE items & Immediate Upcoming.
    """
    today = timezone.localdate()
    next_week = today + timedelta(days=7)

    # 1. WAITING ROOM
    waiting_users = User.objects.filter(groups__isnull=True, is_active=True).exclude(is_superuser=True)

    # 2. PENDING BOOKINGS
    pending_bookings = Booking.objects.filter(status=Booking.STATUS_PENDING).select_related("space", "requested_by").order_by("date", "start_time")

    # 3. UPCOMING SCHEDULE
    upcoming_bookings = Booking.objects.filter(
        status=Booking.STATUS_APPROVED, 
        date__range=[today, next_week]
    ).select_related("space", "requested_by").order_by("date", "start_time")

    stats = {
        "today_total": Booking.objects.filter(date=today).count(),
        "pending": pending_bookings.count(),
        "week_approved": Booking.objects.filter(
            status=Booking.STATUS_APPROVED,
            date__range=[today, today + timedelta(days=6)]
        ).count(),
        "blocked": BlockedDate.objects.count(),
        "waiting_users_count": waiting_users.count()
    }

    # Charts
    chart_spaces = Space.objects.all()
    space_names = [s.name for s in chart_spaces]
    booking_counts = [
        Booking.objects.filter(space=s, status=Booking.STATUS_APPROVED).count()
        for s in chart_spaces
    ]

    return render(request, "admin_dashboard.html", {
        "bookings": pending_bookings, # Pending Only
        "upcoming_bookings": upcoming_bookings, # Next 7 Days Only
        "stats": stats, 
        "all_spaces": chart_spaces,
        "waiting_users": waiting_users,
        "space_names_json": json.dumps(space_names),
        "booking_counts_json": json.dumps(booking_counts),
    })

# ================= Admin History (ANALYTICAL) =================

@user_passes_test(is_dashboard_authorized)
def booking_history(request):
    """
    Full History Page with Filtering and Pagination.
    """
    qs = Booking.objects.select_related("space", "requested_by").order_by("-date", "-start_time")
    
    # Filters
    status = request.GET.get("status")
    space_id = request.GET.get("space_id")
    date_val = request.GET.get("date")

    if status: qs = qs.filter(status=status)
    if space_id: qs = qs.filter(space_id=space_id)
    if date_val: qs = qs.filter(date=date_val)

    # Pagination
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    spaces = Space.objects.all()

    return render(request, "booking_history.html", {
        "page_obj": page_obj,
        "spaces": spaces,
    })

# ================= Admin Actions =================

@user_passes_test(is_dashboard_authorized)
def assign_role(request, user_id):
    if request.method == "POST":
        target_user = get_object_or_404(User, id=user_id)
        role = request.POST.get("role")
        
        if role in ['Faculty', 'Student Rep']:
            group, _ = Group.objects.get_or_create(name=role)
            target_user.groups.add(group)
            messages.success(request, f"Successfully assigned {target_user.username} to {role}.")
        else:
            messages.error(request, "Invalid role selected.")
            
    return redirect("admin_dashboard")

@user_passes_test(is_dashboard_authorized)
def reject_user(request, user_id):
    if request.method == "POST":
        user_to_delete = get_object_or_404(User, id=user_id)
        if not user_to_delete.groups.exists() and not user_to_delete.is_superuser:
            username = user_to_delete.username
            user_to_delete.delete()
            messages.success(request, f"User {username} has been removed.")
        else:
            messages.error(request, "Cannot delete active Faculty/Staff users from here.")
            
    return redirect("admin_dashboard")

@user_passes_test(is_dashboard_authorized)
def approve_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST" and booking.status == Booking.STATUS_PENDING:
        booking.status = Booking.STATUS_APPROVED
        booking.approved_by = request.user
        booking.save()
        
        Notification.objects.create(
            user=booking.requested_by,
            message=f"APPROVED: Your booking for {booking.space.name} on {booking.date} is confirmed."
        )

        if booking.requested_by.email:
            send_notification_email(
                subject="Booking Approved",
                message=f"Good news! Your booking for {booking.space.name} has been APPROVED.",
                recipients=[booking.requested_by.email],
                context_type="hall"
            )

        messages.success(request, "Booking approved.")
    return redirect("admin_dashboard")

@user_passes_test(is_dashboard_authorized)
def reject_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST" and booking.status == Booking.STATUS_PENDING:
        booking.status = Booking.STATUS_REJECTED
        booking.approved_by = request.user
        booking.save()
        
        Notification.objects.create(
            user=booking.requested_by,
            message=f"REJECTED: Your booking for {booking.space.name} on {booking.date} was declined."
        )

        if booking.requested_by.email:
            send_notification_email(
                subject="Booking Request Declined",
                message=f"We regret to inform you that your request for {booking.space.name} has been REJECTED.",
                recipients=[booking.requested_by.email],
                context_type="hall"
            )

        messages.success(request, "Booking rejected.")
    return redirect("admin_dashboard")

@user_passes_test(is_dashboard_authorized)
def admin_cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST":
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        
        if booking.requested_by != request.user:
            if booking.requested_by.email:
                send_notification_email(
                    subject=f"IMPORTANT: Booking Cancelled by Admin",
                    message=f"Your booking for {booking.space.name} on {booking.date} has been CANCELLED by the facility administrator.",
                    recipients=[booking.requested_by.email],
                    context_type="hall"
                )

            Notification.objects.create(
                user=booking.requested_by,
                message=f"CANCELLED: Admin cancelled your booking for {booking.space.name}."
            )
            
        messages.success(request, "Booking cancelled.")
        
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

# ================= RESOURCE MANAGEMENT (NEW) =================

@user_passes_test(is_dashboard_authorized)
def manage_resources(request):
    """
    Dashboard for adding/viewing Spaces, Facilities, and Venue Types.
    """
    spaces = Space.objects.all()
    facilities = Facility.objects.all()
    space_types = SpaceType.objects.all() 
    
    space_form = SpaceForm()
    facility_form = FacilityForm()
    type_form = SpaceTypeForm() 

    if request.method == 'POST':
        if 'add_space' in request.POST:
            space_form = SpaceForm(request.POST, request.FILES)
            if space_form.is_valid():
                space_form.save()
                messages.success(request, "New Space added successfully!")
                return redirect('manage_resources')
            else:
                messages.error(request, "Error adding space. Please check the form.")
        
        elif 'add_facility' in request.POST:
            facility_form = FacilityForm(request.POST)
            if facility_form.is_valid():
                facility_form.save()
                messages.success(request, "New Facility added successfully!")
                return redirect('manage_resources')

        elif 'add_type' in request.POST: 
            type_form = SpaceTypeForm(request.POST)
            if type_form.is_valid():
                type_form.save()
                messages.success(request, "New Venue Type added successfully!")
                return redirect('manage_resources')
            else:
                messages.error(request, "Error adding type. Name must be unique.")

    context = {
        'spaces': spaces,
        'facilities': facilities,
        'space_types': space_types, 
        'space_form': space_form,
        'facility_form': facility_form,
        'type_form': type_form, 
    }
    return render(request, 'manage_resources.html', context)

@user_passes_test(is_dashboard_authorized)
def delete_space(request, pk):
    space = get_object_or_404(Space, pk=pk)
    space_name = space.name
    space.delete()
    messages.warning(request, f"Space '{space_name}' has been deleted.")
    return redirect('manage_resources')

@user_passes_test(is_dashboard_authorized)
def delete_space_type(request, pk):
    """
    Deletes a Venue Type. 
    Strictly protected: will not delete if spaces are linked.
    """
    venue_type = get_object_or_404(SpaceType, pk=pk)
    type_name = venue_type.name
    
    try:
        venue_type.delete()
        messages.warning(request, f"Venue Type '{type_name}' has been removed.")
    except ProtectedError:
        messages.error(
            request, 
            f"Cannot delete '{type_name}' because there are existing spaces assigned to this type. "
            "Please delete or reassign those spaces first."
        )
        
    return redirect('manage_resources')

@user_passes_test(is_dashboard_authorized)
def edit_space_type(request, pk):
    """
    Simple edit view for SpaceType.
    """
    venue_type = get_object_or_404(SpaceType, pk=pk)
    
    if request.method == 'POST':
        form = SpaceTypeForm(request.POST, instance=venue_type)
        if form.is_valid():
            form.save()
            messages.success(request, f"Venue Type updated to '{venue_type.name}'")
            return redirect('manage_resources')
    else:
        form = SpaceTypeForm(instance=venue_type)

    return render(request, 'edit_space_type.html', {'form': form, 'type': venue_type})

# === NEW: FACILITY EDIT & DELETE ACTIONS ===

@user_passes_test(is_dashboard_authorized)
def delete_facility(request, pk):
    """
    Deletes a Facility.
    """
    facility = get_object_or_404(Facility, pk=pk)
    name = facility.name
    facility.delete()
    messages.warning(request, f"Facility '{name}' has been deleted from inventory.")
    return redirect('manage_resources')

@user_passes_test(is_dashboard_authorized)
def edit_facility(request, pk):
    """
    Edit a Facility name.
    """
    facility = get_object_or_404(Facility, pk=pk)
    
    if request.method == 'POST':
        form = FacilityForm(request.POST, instance=facility)
        if form.is_valid():
            form.save()
            messages.success(request, f"Facility updated to '{facility.name}'")
            return redirect('manage_resources')
    else:
        form = FacilityForm(instance=facility)

    return render(request, 'edit_facility.html', {'form': form, 'facility': facility})

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
def api_space_facilities(request):
    space_id = request.GET.get("space_id")
    if not space_id:
        return JsonResponse([], safe=False)
    
    space = get_object_or_404(Space, id=space_id)
    facilities = space.facilities.all().values("id", "name")
    
    return JsonResponse(list(facilities), safe=False)

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
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save()
    
    if request.user.is_staff or is_dashboard_authorized(request.user):
        if "BUS" in notif.message or "Bus" in notif.message:
            return redirect('bus_list')
        return redirect('admin_dashboard')
    else:
        if "BUS" in notif.message or "Bus" in notif.message:
            return redirect('bus_list')
        return redirect('my_bookings')

@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'notifications.html', {'notifications': notifications})

def logout_view(request):
    logout(request)
    return redirect("home")

# ================= BUS SYSTEM =================

@login_required
def bus_list(request):
    is_officer = is_transport_officer(request.user)
    
    if is_officer:
        bookings = BusBooking.objects.all().order_by('-date')
    else:
        bookings = BusBooking.objects.filter(requested_by=request.user).order_by('-date')
    
    buses = Bus.objects.all()
    
    return render(request, "bus_list.html", {
        "bookings": bookings, 
        "buses": buses,
        "is_transport_officer": is_officer
    })

@login_required
@approval_required
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
            status='Pending'
        )
        
        officers = User.objects.filter(groups__name='Transport')
        officer_emails = [u.email for u in officers if u.email]

        send_notification_email(
            subject=f"New Bus Request: {origin} to {destination}",
            message=f"User {request.user.username} requested a bus on {date_str}.\nRoute: {origin} -> {destination}",
            recipients=officer_emails,
            context_type="bus"
        )

        if request.user.email:
            send_notification_email(
                subject="Bus Request Received",
                message=f"Dear {request.user.username},\n\nYour bus request has been received.",
                recipients=[request.user.email],
                context_type="bus"
            )

        for officer in officers:
            Notification.objects.create(
                user=officer, 
                message=f"New BUS Request: {request.user.username}"
            )
            
        messages.success(request, "Bus request submitted to Transport Officer.")
        return redirect("bus_list")
        
    return render(request, "book_bus.html", {"buses": buses})

# === TRANSPORT OFFICER ACTIONS ===

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

        if booking.requested_by.email:
            send_notification_email(
                subject="Bus Booking Rejected",
                message=f"Your bus trip to {booking.destination} on {booking.date} was unavailable.",
                recipients=[booking.requested_by.email],
                context_type="bus"
            )

        messages.success(request, "Bus booking rejected.")
    return redirect("bus_list")

@login_required
def cancel_bus_booking(request, booking_id):
    booking = get_object_or_404(BusBooking, id=booking_id)
    is_officer = is_transport_officer(request.user)
    is_owner = booking.requested_by == request.user

    if not (is_owner or is_officer):
        messages.error(request, "You do not have permission to cancel this booking.")
        return redirect("bus_list")

    if request.method == "POST":
        booking.status = BusBooking.STATUS_CANCELLED
        booking.save()

        # Notify based on who cancelled
        if is_owner and not is_officer:
            officers = User.objects.filter(groups__name='Transport')
            officer_emails = [u.email for u in officers if u.email]
            send_notification_email(
                subject=f"Bus Trip Cancelled: {booking.destination}",
                message=f"FYI: {request.user.username} has CANCELLED their bus request.",
                recipients=officer_emails,
                context_type="bus"
            )
            for officer in officers:
                Notification.objects.create(
                    user=officer,
                    message=f"CANCELLED: {request.user.username} cancelled bus."
                )

        elif is_officer:
            if booking.requested_by.email:
                send_notification_email(
                    subject="Bus Trip Cancelled by Officer",
                    message=f"Important: The Transport Officer has cancelled your bus trip.",
                    recipients=[booking.requested_by.email],
                    context_type="bus"
                )
            Notification.objects.create(
                user=booking.requested_by,
                message=f"ALERT: Officer cancelled your bus to {booking.destination}"
            )

        messages.success(request, "Bus booking cancelled successfully.")

    return redirect("bus_list")

# ================= TIMETABLE AUTOMATION =================

@user_passes_test(is_dashboard_authorized)
def upload_timetable(request):
    spaces = Space.objects.all()
    
    if request.method == "POST":
        space_id = request.POST.get("space_id")
        day_of_week = int(request.POST.get("day_of_week"))
        expected_count = request.POST.get("expected_count") or 0
        
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

@user_passes_test(is_dashboard_authorized)
def clear_timetable(request):
    if request.method == "POST":
        subject_name = request.POST.get("subject_name")
        if not subject_name:
            messages.error(request, "Subject name is required.")
            return redirect("upload_timetable")

        today = timezone.localdate()
        targets = Booking.objects.filter(
            purpose__iexact=f"TIMETABLE: {subject_name}",
            date__gte=today,
            status=Booking.STATUS_APPROVED
        )
        
        count = targets.count()
        if count > 0:
            targets.delete()
            messages.success(request, f"Successfully deleted {count} future bookings for '{subject_name}'.")
        else:
            messages.warning(request, f"No future bookings found.")
            
    return redirect("upload_timetable")

# ================= LOGIN =================

def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            if is_transport_officer(user):
                return redirect('bus_list')
            
            next_url = request.POST.get('next')
            if not next_url:
                next_url = 'home'
            
            return redirect(next_url)
    else:
        form = AuthenticationForm()
    
    return render(request, "login.html", {"form": form})