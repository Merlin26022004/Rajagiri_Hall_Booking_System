import json
from datetime import timedelta, date
from django.contrib import messages
from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib.auth.models import User, Group
# FIX: Added transaction for race condition protection
from django.db import transaction
# FIX: Added Case, When, Value, IntegerField for explicit priority sorting
from django.db.models import Q, ProtectedError, Case, When, Value, IntegerField
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.core.paginator import Paginator 
from django.conf import settings

# === CUSTOM IMPORTS ===
from .models import Space, Booking, BlockedDate, Notification, Bus, BusBooking, Facility, SpaceType
from .decorators import approval_required
from .forms import SpaceForm, FacilityForm, SpaceTypeForm, RescheduleForm

# Safe Import for Utils with Fallback
try:
    from .utils import calculate_business_deadline
except ImportError:
    def calculate_business_deadline(start_dt):
        return start_dt + timedelta(hours=24)

# ================= Helpers =================

def is_dashboard_authorized(user):
    if user.is_superuser: return True
    return user.groups.filter(name__in=['Faculty', 'Admin']).exists()

def is_transport_officer(user):
    return user.groups.filter(name='Transport').exists()

def send_notification_email(subject, message, recipients, context_type="hall"):
    if not recipients: return
    sender_email = settings.EMAIL_HOST_USER
    from_email = f"Rajagiri Facility Management <{sender_email}>" if context_type == "hall" else (f"Rajagiri Transport Officer <{sender_email}>" if context_type == "bus" else sender_email)
    try:
        send_mail(subject, message, from_email, recipients, fail_silently=True)
    except Exception as e:
        print(f"Email Error: {e}")

# === QUEUE MANAGER (UPDATED FOR PRIORITY & SAFETY) ===
def promote_next_waitlisted(cancelled_booking):
    """
    Finds the next waitlisted user for the cancelled slot.
    PRIORITY FIX: Uses explicit Case/When annotation.
    SAFETY FIX: Uses transaction.atomic and select_for_update.
    PERFORMANCE FIX: Sends emails AFTER transaction commits to prevent DB locks.
    """
    promoted_booking = None
    user_email_params = None
    admin_email_params = None

    with transaction.atomic():
        # Find next overlap in queue, locking the rows to prevent double-promotion
        next_in_line = Booking.objects.select_for_update().filter(
            space=cancelled_booking.space,
            date=cancelled_booking.date,
            status=Booking.STATUS_WAITLISTED
        ).filter(
            # Check time overlap
            Q(start_time__lt=cancelled_booking.end_time, end_time__gt=cancelled_booking.start_time)
        ).annotate(
            # FIX: Assign explicit numeric priority (External=1, Internal=2, Others=3)
            priority_rank=Case(
                When(resource_type='External', then=Value(1)),
                When(resource_type='Internal', then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by('priority_rank', 'created_at').first()

        if next_in_line:
            promoted_booking = next_in_line
            
            # 1. Promote Status
            next_in_line.status = Booking.STATUS_PENDING
            # 2. Reset Business Clock (Fresh 24h start)
            next_in_line.approval_deadline = calculate_business_deadline(timezone.now())
            next_in_line.save()
            
            # 3. Notify User (DB Operation)
            msg = f"Good News! A slot has opened up for {next_in_line.space.name}. Your request is now actively Pending approval."
            Notification.objects.create(user=next_in_line.requested_by, message=f"Promoted: Your booking for {next_in_line.space.name} is now Pending.")
            
            # 4. Prepare Email Data (Don't send inside transaction)
            if next_in_line.requested_by.email:
                user_email_params = {
                    'subject': "Booking Update: You've Moved Up!",
                    'message': f"{msg}\n\nNew Deadline for Admin Action: {next_in_line.approval_deadline.strftime('%d %b, %I:%M %p')}",
                    'recipients': [next_in_line.requested_by.email]
                }
                
            # 5. Prepare Admin Email Data
            facility_admins = User.objects.filter(is_superuser=True)
            admin_emails = [u.email for u in facility_admins if u.email]
            if admin_emails:
                admin_email_params = {
                    'subject': f"Queue Update: New Active Request for {next_in_line.space.name}",
                    'message': f"Previous booking was cancelled/rejected. The next user ({next_in_line.requested_by.username}) has been promoted to Pending.",
                    'recipients': admin_emails
                }

    # === SEND EMAILS (Outside Transaction) ===
    if user_email_params:
        send_notification_email(user_email_params['subject'], user_email_params['message'], user_email_params['recipients'], "hall")
    
    if admin_email_params:
        send_notification_email(admin_email_params['subject'], admin_email_params['message'], admin_email_params['recipients'], "hall")

    return promoted_booking

# ================= Public / Home =================

def home(request):
    if request.user.is_authenticated and is_transport_officer(request.user):
        return redirect('bus_list')

    spaces = Space.objects.all()[:6]
    today = timezone.localdate()
    
    stats = {"today_total": 0, "pending": 0, "week_approved": 0, "blocked": BlockedDate.objects.filter(date__gte=today).count()}

    if request.user.is_authenticated:
        if request.user.is_staff or is_dashboard_authorized(request.user):
            today_total = Booking.objects.filter(date=today).count()
            pending = Booking.objects.filter(status=Booking.STATUS_PENDING).count()
            week_approved = Booking.objects.filter(
                status=Booking.STATUS_APPROVED,
                date__range=[today, today + timedelta(days=6)]
            ).count()
        else:
            today_total = Booking.objects.filter(requested_by=request.user, date=today).count()
            pending = Booking.objects.filter(requested_by=request.user, status=Booking.STATUS_PENDING).count()
            week_approved = Booking.objects.filter(
                requested_by=request.user,
                status=Booking.STATUS_APPROVED,
                date__range=[today, today + timedelta(days=6)]
            ).count()
        stats.update({"today_total": today_total, "pending": pending, "week_approved": week_approved})

    return render(request, "index.html", {"spaces": spaces, "stats": stats})

def space_list(request):
    return render(request, "spaces.html", {"spaces": Space.objects.all()})

def space_availability(request, space_id):
    space = get_object_or_404(Space, pk=space_id)
    today = timezone.localdate()
    bookings = Booking.objects.filter(space=space, date__gte=today).order_by("date", "start_time").select_related("requested_by", "approved_by")
    blocked_dates = BlockedDate.objects.filter(Q(space=space) | Q(space__isnull=True), date__gte=today).order_by("date")
    return render(request, "space_availability.html", {"space": space, "bookings": bookings, "blocked_dates": blocked_dates})

# ================= CORE BOOKING LOGIC =================

@login_required
@approval_required
def book_space(request):
    spaces = Space.objects.all()
    facilities = Facility.objects.all()
    selected_space = None

    if request.GET.get("space_id"):
        try: selected_space = Space.objects.get(id=request.GET.get("space_id"))
        except Space.DoesNotExist: pass

    if request.method == "POST":
        space_id = request.POST.get("space_id")
        date_str = request.POST.get("date")
        start_time_str = request.POST.get("start_time")
        end_time_str = request.POST.get("end_time")
        expected_count = request.POST.get("expected_count")
        purpose = request.POST.get("purpose")
        faculty_name = request.POST.get("faculty_in_charge")
        
        # === NEW PRIORITY FIELDS ===
        resource_type = request.POST.get("resource_type", Booking.RESOURCE_INTERNAL)
        resource_name = request.POST.get("resource_name", "")
        resource_number = request.POST.get("resource_number", "")
        
        selected_facility_ids = request.POST.getlist("facilities")

        if not all([space_id, date_str, start_time_str, end_time_str, expected_count, purpose]):
            messages.error(request, "Please fill all required fields.")
            return redirect("book_space")

        if not request.user.is_staff and not faculty_name:
            messages.error(request, "Students must specify the Faculty In-Charge.")
            return redirect("book_space")
            
        # Validation for External Resource
        if resource_type == Booking.RESOURCE_EXTERNAL:
            if not resource_name or not resource_number:
                messages.error(request, "External Events require Resource Name and Contact Number.")
                return redirect("book_space")

        space = get_object_or_404(Space, id=space_id)
        d, st, et = parse_date(date_str), parse_time(start_time_str), parse_time(end_time_str)

        # Validation
        try:
            if int(expected_count) > space.capacity:
                messages.error(request, "Count exceeds capacity."); return redirect("book_space")
        except ValueError: messages.error(request, "Invalid count."); return redirect("book_space")

        if d < timezone.localdate() or not (d and st and et) or et <= st:
            messages.error(request, "Invalid date/time."); return redirect("book_space")

        if BlockedDate.objects.filter(Q(space=space) | Q(space__isnull=True), date=d).exists():
            messages.error(request, "Date blocked."); return redirect("book_space")

        # === QUEUE & CONFLICT LOGIC ===
        
        # Check for ANY overlap
        conflicting_bookings = Booking.objects.filter(
            space=space, date=d,
            status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED, Booking.STATUS_WAITLISTED]
        ).filter(Q(start_time__lt=et, end_time__gt=st))

        # Check specifically for APPROVED conflicts (The hard block)
        approved_conflicts = conflicting_bookings.filter(status=Booking.STATUS_APPROVED)
        
        # === FEATURE 1: PRIORITY CHECK ===
        can_waitlist = True
        
        if approved_conflicts.exists():
            blocker = approved_conflicts.first()
            
            # Logic: If I am External AND Blocker is Internal -> I can jump queue (Waitlist)
            # Logic: If Blocker is External -> NO ONE can jump (Hard Block)
            
            is_my_request_external = (resource_type == Booking.RESOURCE_EXTERNAL)
            is_blocker_internal = (blocker.resource_type == Booking.RESOURCE_INTERNAL)
            
            if is_my_request_external and is_blocker_internal:
                # Priority Override Allowed
                can_waitlist = True
                messages.warning(request, "Slot occupied by Internal Event. As an External request, you have been placed at the TOP of the Waitlist.")
            else:
                can_waitlist = False # Hard Block

        if not can_waitlist:
            # === FEATURE 2: TRANSPARENCY (Show who is blocking) ===
            blocker = approved_conflicts.first()
            
            # Construct Blocker Message based on Privacy Rules
            if blocker.resource_type == Booking.RESOURCE_EXTERNAL:
                # External: Show Resource Name & Number (Safe, usually public figure/coord)
                msg_detail = f"Dignitary: {blocker.resource_name} (Contact: {blocker.resource_number})"
            else:
                # Internal: Show User Name & Email (Protect Phone)
                msg_detail = f"Booked by: {blocker.requested_by.username} ({blocker.requested_by.email})"
            
            messages.error(request, f"Slot BUSY. {msg_detail}. Event: {blocker.purpose}")
            return redirect("book_space")

        # === QUEUE PLACEMENT ===
        is_waitlisted = conflicting_bookings.exists()
        
        status = Booking.STATUS_WAITLISTED if is_waitlisted else Booking.STATUS_PENDING
        deadline = None if is_waitlisted else calculate_business_deadline(timezone.now())

        booking = Booking.objects.create(
            space=space, requested_by=request.user, date=d, start_time=st, end_time=et,
            expected_count=int(expected_count), purpose=purpose,
            status=status, approved_by=None, faculty_in_charge=faculty_name,
            approval_deadline=deadline,
            resource_type=resource_type,
            resource_name=resource_name,
            resource_number=resource_number
        )
        if selected_facility_ids: booking.requested_facilities.set(selected_facility_ids)

        # Notifications
        facility_admins = User.objects.filter(is_superuser=True)
        admin_emails = [u.email for u in facility_admins if u.email]

        if is_waitlisted:
            position = booking.queue_position
            messages.warning(request, f"Slot busy. You are #{position} on the Waitlist.")
            
            # If priority override happened, notify admin specifically
            if resource_type == Booking.RESOURCE_EXTERNAL:
                send_notification_email("PRIORITY WAITLIST ALERT", f"High Priority External Request from {request.user.username} is waitlisted behind an Internal event.", admin_emails, "hall")
                
            if request.user.email:
                send_notification_email("Added to Waitlist", f"Your request is waitlisted (Position #{position}). We will notify you if the slot opens.", [request.user.email], "hall")
        else:
            deadline_fmt = deadline.strftime("%A, %d %b at %I:%M %p")
            messages.success(request, f"Request Pending. Deadline: {deadline_fmt}")
            if admin_emails:
                send_notification_email(f"ACTION REQUIRED: {space.name}", f"New PENDING request from {request.user.username}.\nDeadline: {deadline_fmt}", admin_emails, "hall")
            if request.user.email:
                send_notification_email("Request Received", f"Your booking is Pending approval.\nDeadline: {deadline_fmt}", [request.user.email], "hall")
            for admin in facility_admins:
                Notification.objects.create(user=admin, message=f"New Request: {request.user.username} for {space.name}")

        return redirect("my_bookings")

    return render(request, "booking_form.html", {"spaces": spaces, "selected_space": selected_space, "facilities": facilities})

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(requested_by=request.user).order_by("-date", "-created_at")
    return render(request, "my_bookings.html", {"bookings": bookings})

# === FEATURE 3: RESCHEDULE BOOKING ===
@login_required
def reschedule_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Permission Check
    if booking.requested_by != request.user and not request.user.is_superuser:
        messages.error(request, "You are not authorized to edit this booking.")
        return redirect("my_bookings")

    if request.method == "POST":
        form = RescheduleForm(request.POST, instance=booking)
        if form.is_valid():
            # ========================================================
            # FIX: Fetch fresh DB copy to get the ACTUAL old values
            # ========================================================
            current_db_booking = Booking.objects.get(id=booking.id)
            
            old_space = current_db_booking.space
            old_date = current_db_booking.date
            old_start = current_db_booking.start_time
            old_end = current_db_booking.end_time
            # ========================================================
            
            # Temporary object with new data (don't save yet)
            new_data = form.save(commit=False)

            # FIX: Check Blocked Dates specifically for Reschedule
            if BlockedDate.objects.filter(Q(space=booking.space) | Q(space__isnull=True), date=new_data.date).exists():
                messages.error(request, "The selected date is administratively blocked.")
                return redirect("reschedule_booking", booking_id=booking.id)
            
            # 2. Check Availability for NEW slot
            conflicting = Booking.objects.filter(
                space=booking.space,
                date=new_data.date,
                status__in=[Booking.STATUS_APPROVED, Booking.STATUS_PENDING]
            ).filter(
                Q(start_time__lt=new_data.end_time, end_time__gt=new_data.start_time)
            ).exclude(id=booking.id) # Exclude self
            
            if conflicting.exists():
                messages.error(request, "The new date/time is unavailable. Please choose another.")
            else:
                # 3. Save Changes
                form.save()
                messages.success(request, "Rescheduled successfully.")
                
                # 4. Trigger Promotion on the OLD slot
                class OldSlotStub:
                    def __init__(self, space, date, start, end):
                        self.space = space
                        self.date = date
                        self.start_time = start
                        self.end_time = end
                
                # Instantiate with the DB captured variables
                stub = OldSlotStub(old_space, old_date, old_start, old_end)
                promote_next_waitlisted(stub)
                
                return redirect("my_bookings")
    else:
        form = RescheduleForm(instance=booking)

    return render(request, "reschedule_booking.html", {"form": form, "booking": booking})

@login_required
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, requested_by=request.user)
    
    if request.method == "POST" and booking.can_cancel:
        # Check if this booking was "blocking" the slot (Approved or Pending)
        was_blocking = booking.status in [Booking.STATUS_PENDING, Booking.STATUS_APPROVED]
        
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        messages.success(request, "Booking cancelled.")
        
        # Notify Admins
        facility_admins = User.objects.filter(is_superuser=True)
        admin_emails = [u.email for u in facility_admins if u.email]
        send_notification_email(f"Cancelled: {booking.space.name}", f"{request.user.username} cancelled.", admin_emails, "hall")
        
        # === PROMOTION LOGIC ===
        if was_blocking:
            promote_next_waitlisted(booking)

    return redirect("my_bookings")

# ================= Admin Dashboard & Actions =================

@user_passes_test(is_dashboard_authorized)
def admin_dashboard(request):
    now = timezone.now()
    
    # === LAZY ENFORCER 1: PENDING EXPIRY ===
    expired_bookings = Booking.objects.filter(status=Booking.STATUS_PENDING, approval_deadline__lt=now, auto_expired=False)
    if expired_bookings.exists():
        count = 0
        for b in expired_bookings:
            b.status = Booking.STATUS_REJECTED
            b.auto_expired = True
            b.save()
            count += 1
            Notification.objects.create(user=b.requested_by, message=f"EXPIRED: Booking for {b.space.name}")
            # Promote next user if one exists
            promote_next_waitlisted(b)
        if count > 0: messages.warning(request, f"System: {count} bookings expired. Queue updated.")

    # === LAZY ENFORCER 2: PAST WAITLIST CLEANUP ===
    # If the requested date has passed and user is still Waitlisted, reject them to clean DB.
    expired_waitlist = Booking.objects.filter(status=Booking.STATUS_WAITLISTED, date__lt=now.date())
    if expired_waitlist.exists():
        w_count = expired_waitlist.count()
        expired_waitlist.update(status=Booking.STATUS_REJECTED, auto_expired=True)
        # No need to notify loudly, just clean up.

    # === VIEW DATA ===
    today = timezone.localdate()
    next_week = today + timedelta(days=7)
    
    # CRITICAL UPDATE: Apply Priority Logic to Admin View as well
    action_queue = Booking.objects.filter(
        status__in=[Booking.STATUS_PENDING, Booking.STATUS_WAITLISTED]
    ).annotate(
        # FIX: Admin sees same priority as system
        priority_rank=Case(
            When(resource_type='External', then=Value(1)),
            When(resource_type='Internal', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).select_related("space", "requested_by").order_by("date", "start_time", "priority_rank", "created_at")

    upcoming_bookings = Booking.objects.filter(status=Booking.STATUS_APPROVED, date__range=[today, next_week]).select_related("space", "requested_by").order_by("date", "start_time")
    
    stats = {
        "today_total": Booking.objects.filter(date=today).count(),
        "pending": Booking.objects.filter(status=Booking.STATUS_PENDING).count(),
        "blocked": BlockedDate.objects.count(),
        "waiting_users_count": User.objects.filter(groups__isnull=True, is_active=True).exclude(is_superuser=True).count()
    }
    
    chart_spaces = Space.objects.all()
    space_names = [s.name for s in chart_spaces]
    booking_counts = [Booking.objects.filter(space=s, status=Booking.STATUS_APPROVED).count() for s in chart_spaces]

    return render(request, "admin_dashboard.html", {
        "bookings": action_queue, 
        "upcoming_bookings": upcoming_bookings, 
        "stats": stats,
        "all_spaces": chart_spaces, 
        "waiting_users": User.objects.filter(groups__isnull=True, is_active=True).exclude(is_superuser=True),
        "space_names_json": json.dumps(space_names), 
        "booking_counts_json": json.dumps(booking_counts), 
        "now": now
    })

@user_passes_test(is_dashboard_authorized)
def booking_history(request):
    qs = Booking.objects.select_related("space", "requested_by").order_by("-date", "-start_time")
    status, space_id, date_val = request.GET.get("status"), request.GET.get("space_id"), request.GET.get("date")
    if status: qs = qs.filter(status=status)
    if space_id: qs = qs.filter(space_id=space_id)
    if date_val: qs = qs.filter(date=date_val)
    
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, "booking_history.html", {"page_obj": page_obj, "spaces": Space.objects.all()})

@user_passes_test(is_dashboard_authorized)
def approve_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    # 1. SECURITY: Only process if status is valid for approval
    if request.method == "POST" and booking.status in [Booking.STATUS_PENDING, Booking.STATUS_WAITLISTED]:
        
        # 2. CONFLICT CHECK: Find ALL Approved/Pending bookings holding this slot
        blocking_bookings = Booking.objects.filter(
            space=booking.space,
            date=booking.date,
            status__in=[Booking.STATUS_APPROVED, Booking.STATUS_PENDING]
        ).filter(
            Q(start_time__lt=booking.end_time, end_time__gt=booking.start_time)
        ).exclude(id=booking.id)

        # 3. GOD MODE: Loop through ALL blockers and BUMP them to Waitlist
        if blocking_bookings.exists():
            count = 0
            for blocker in blocking_bookings:
                # BUMP TO WAITLIST instead of Rejecting
                blocker.status = Booking.STATUS_WAITLISTED 
                # Reset approval info just in case
                blocker.approved_by = None
                blocker.approval_deadline = None 
                blocker.save()
                count += 1
                
                # Notify the person who got bumped
                Notification.objects.create(
                    user=blocker.requested_by, 
                    message=f"ALERT: Your booking for {blocker.space.name} was moved to Waitlist due to a Priority Event."
                )
                if blocker.requested_by.email:
                    send_notification_email(
                        "Booking Moved to Waitlist", 
                        f"Your booking for {blocker.space.name} on {blocker.date} has been moved to the Waitlist to accommodate a high-priority institutional event.\n\nIf the slot becomes free, you will be automatically notified.", 
                        [blocker.requested_by.email], 
                        "hall"
                    )
            
            messages.warning(request, f"Note: {count} conflicting booking(s) were moved to the Waitlist.")

        # 4. APPROVE the requested booking
        booking.status = Booking.STATUS_APPROVED
        booking.approved_by = request.user
        booking.save()
        
        Notification.objects.create(user=booking.requested_by, message=f"APPROVED: {booking.space.name}")
        if booking.requested_by.email: send_notification_email("Booking Approved", f"Your booking for {booking.space.name} is confirmed.", [booking.requested_by.email], "hall")

        # 5. NOTIFY STANDBY USERS (The remaining waitlist)
        waitlisted_users = Booking.objects.filter(
            space=booking.space, date=booking.date, status=Booking.STATUS_WAITLISTED
        ).filter(Q(start_time__lt=booking.end_time, end_time__gt=booking.start_time))
        
        for wb in waitlisted_users:
            Notification.objects.create(user=wb.requested_by, message=f"Standby: {booking.space.name} approved for another. You are on waitlist.")
            if wb.requested_by.email:
                send_notification_email("Waitlist Update: On Standby", f"The slot for {booking.space.name} has been confirmed for another user. You remain on the waitlist in case of cancellation.", [wb.requested_by.email], "hall")

        messages.success(request, "Booking approved. Conflicting bookings were handled.")
    
    # Smart Redirect
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

@user_passes_test(is_dashboard_authorized)
def reject_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    # UPDATE: Allow rejection of WAITLISTED items
    if request.method == "POST" and booking.status in [Booking.STATUS_PENDING, Booking.STATUS_WAITLISTED]:
        booking.status = Booking.STATUS_REJECTED
        booking.approved_by = request.user
        booking.save()
        
        Notification.objects.create(user=booking.requested_by, message=f"REJECTED: {booking.space.name}")
        if booking.requested_by.email: send_notification_email("Booking Rejected", f"Your request for {booking.space.name} was declined.", [booking.requested_by.email], "hall")

        # === PROMOTE NEXT USER ===
        promote_next_waitlisted(booking)

        messages.success(request, "Booking rejected. Queue updated.")
    
    # Smart Redirect
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

@user_passes_test(is_dashboard_authorized)
def admin_cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == "POST":
        # Check if we need to promote someone (if this booking was holding the slot)
        was_blocking = booking.status in [Booking.STATUS_APPROVED, Booking.STATUS_PENDING]
        
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        
        if booking.requested_by != request.user:
            if booking.requested_by.email: send_notification_email("Booking Cancelled by Admin", f"Your booking for {booking.space.name} was cancelled.", [booking.requested_by.email], "hall")
            Notification.objects.create(user=booking.requested_by, message=f"CANCELLED: Admin cancelled your booking.")
        
        # === TRIGGER PROMOTION ===
        if was_blocking:
            promote_next_waitlisted(booking)
        
        messages.success(request, "Booking cancelled.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

@user_passes_test(is_dashboard_authorized)
def assign_role(request, user_id):
    if request.method == "POST":
        target = get_object_or_404(User, id=user_id)
        role = request.POST.get("role")
        if role in ['Faculty', 'Student Rep']:
            g, _ = Group.objects.get_or_create(name=role)
            target.groups.add(g)
            messages.success(request, f"Assigned {target.username} to {role}.")
        else: messages.error(request, "Invalid role.")
    return redirect("admin_dashboard")

@user_passes_test(is_dashboard_authorized)
def reject_user(request, user_id):
    if request.method == "POST":
        user_to_del = get_object_or_404(User, id=user_id)
        if not user_to_del.groups.exists() and not user_to_del.is_superuser:
            user_to_del.delete(); messages.success(request, "User removed.")
        else: messages.error(request, "Cannot delete active Faculty/Staff.")
    return redirect("admin_dashboard")

# ================= Resource & Bus =================

@user_passes_test(is_dashboard_authorized)
def manage_resources(request):
    spaces = Space.objects.all(); facilities = Facility.objects.all(); space_types = SpaceType.objects.all()
    if request.method == 'POST':
        if 'add_space' in request.POST:
            f = SpaceForm(request.POST, request.FILES)
            if f.is_valid(): f.save(); messages.success(request, "Space added!")
        elif 'add_facility' in request.POST:
            f = FacilityForm(request.POST)
            if f.is_valid(): f.save(); messages.success(request, "Facility added!")
        elif 'add_type' in request.POST:
            f = SpaceTypeForm(request.POST)
            if f.is_valid(): f.save(); messages.success(request, "Type added!")
            else: messages.error(request, "Error adding type.")
        return redirect('manage_resources')
    return render(request, 'manage_resources.html', {'spaces': spaces, 'facilities': facilities, 'space_types': space_types, 'space_form': SpaceForm(), 'facility_form': FacilityForm(), 'type_form': SpaceTypeForm()})

@user_passes_test(is_dashboard_authorized)
def delete_space(request, pk): 
    space = get_object_or_404(Space, pk=pk)
    name = space.name
    space.delete()
    messages.warning(request, f"Space '{name}' has been deleted.")
    return redirect('manage_resources')

@user_passes_test(is_dashboard_authorized)
def delete_space_type(request, pk): 
    try: 
        get_object_or_404(SpaceType, pk=pk).delete()
        messages.warning(request, "Venue Type removed.")
    except ProtectedError: messages.error(request, "Cannot delete used type.")
    return redirect('manage_resources')

@user_passes_test(is_dashboard_authorized)
def edit_space_type(request, pk):
    obj = get_object_or_404(SpaceType, pk=pk)
    if request.method=='POST': 
        f=SpaceTypeForm(request.POST, instance=obj)
        if f.is_valid(): f.save(); return redirect('manage_resources')
    return render(request, 'edit_space_type.html', {'form': SpaceTypeForm(instance=obj), 'type': obj})

@user_passes_test(is_dashboard_authorized)
def delete_facility(request, pk): 
    fac = get_object_or_404(Facility, pk=pk)
    name = fac.name
    fac.delete()
    messages.warning(request, f"Facility '{name}' deleted.")
    return redirect('manage_resources')

@user_passes_test(is_dashboard_authorized)
def edit_facility(request, pk):
    obj = get_object_or_404(Facility, pk=pk)
    if request.method=='POST': 
        f=FacilityForm(request.POST, instance=obj)
        if f.is_valid(): f.save(); return redirect('manage_resources')
    return render(request, 'edit_facility.html', {'form': FacilityForm(instance=obj), 'facility': obj})

# === API ===
@require_GET
@login_required
def api_unavailable_dates(request):
    sid = request.GET.get("space_id")
    if not sid: return JsonResponse([], safe=False)
    blocked = BlockedDate.objects.filter(Q(space_id=sid)|Q(space__isnull=True), date__gte=timezone.localdate()).values_list("date", flat=True)
    return JsonResponse([d.isoformat() for d in blocked], safe=False)

@require_GET
@login_required
def api_space_facilities(request):
    sid = request.GET.get("space_id")
    if not sid: return JsonResponse([], safe=False)
    space = get_object_or_404(Space, id=sid)
    return JsonResponse(list(space.facilities.all().values("id", "name")), safe=False)

@require_GET
@login_required
def space_day_slots(request):
    sid, d = request.GET.get("space_id"), request.GET.get("date")
    if not (sid and d): return JsonResponse([], safe=False)
    # Only show PENDING/APPROVED as taken. Waitlisted is free to join queue.
    bookings = Booking.objects.filter(space_id=sid, date=d, status__in=[Booking.STATUS_PENDING, Booking.STATUS_APPROVED]).values("start_time", "end_time")
    return JsonResponse([{"start": str(b["start_time"]), "end": str(b["end_time"])} for b in bookings], safe=False)

def calendar_view(request): return render(request, "calendar.html")
def api_bookings(request):
    bookings = Booking.objects.filter(status=Booking.STATUS_APPROVED)
    return JsonResponse([{'title': f"{b.space.name}", 'start': f"{b.date}T{b.start_time}", 'end': f"{b.date}T{b.end_time}", 'color': '#0d6efd'} for b in bookings], safe=False)

# === NOTIFICATIONS ===
@login_required
def mark_notification_read(request, notif_id):
    n = get_object_or_404(Notification, id=notif_id, user=request.user); n.is_read=True; n.save()
    if "bus" in n.message.lower(): return redirect('bus_list')
    if request.user.is_staff or is_dashboard_authorized(request.user): return redirect('admin_dashboard')
    return redirect('my_bookings')

@login_required
def notification_list(request): return render(request, 'notifications.html', {'notifications': Notification.objects.filter(user=request.user).order_by('-created_at')})

# === BUS ===
@login_required
def bus_list(request):
    is_officer = is_transport_officer(request.user)
    qs = BusBooking.objects.all() if is_officer else BusBooking.objects.filter(requested_by=request.user)
    return render(request, "bus_list.html", {"bookings": qs.order_by('-date'), "buses": Bus.objects.all(), "is_transport_officer": is_officer})

@login_required
@approval_required
def book_bus(request):
    if request.method=="POST":
        d = request.POST
        if not all([d.get(k) for k in ['bus_id','date','start_time','end_time','origin','destination']]): messages.error(request,"Fill fields"); return redirect("book_bus")
        BusBooking.objects.create(bus_id=d['bus_id'], requested_by=request.user, date=d['date'], start_time=d['start_time'], end_time=d['end_time'], origin=d['origin'], destination=d['destination'], purpose=d['purpose'])
        officers = User.objects.filter(groups__name='Transport')
        recipients = [u.email for u in officers if u.email]
        send_notification_email(f"Bus Request: {d['destination']}", f"User {request.user.username} requested bus.", recipients, "bus")
        if request.user.email: send_notification_email("Bus Request Received", f"Request for {d['destination']} received.", [request.user.email], "bus")
        for o in officers: Notification.objects.create(user=o, message=f"Bus Req: {request.user.username}")
        messages.success(request, "Bus request submitted."); return redirect("bus_list")
    return render(request, "book_bus.html", {"buses": Bus.objects.all()})

@user_passes_test(is_transport_officer)
def approve_bus_booking(request, booking_id):
    b = get_object_or_404(BusBooking, id=booking_id)
    if request.method=="POST":
        b.status='Approved'; b.save()
        Notification.objects.create(user=b.requested_by, message=f"BUS APPROVED: {b.destination}")
        if b.requested_by.email: send_notification_email("Bus Approved", "Trip confirmed.", [b.requested_by.email], "bus")
        messages.success(request, "Bus approved.")
    return redirect("bus_list")

@user_passes_test(is_transport_officer)
def reject_bus_booking(request, booking_id):
    b = get_object_or_404(BusBooking, id=booking_id)
    if request.method=="POST":
        b.status='Rejected'; b.save()
        Notification.objects.create(user=b.requested_by, message=f"BUS REJECTED: {b.destination}")
        if b.requested_by.email: send_notification_email("Bus Rejected", "Trip unavailable.", [b.requested_by.email], "bus")
        messages.success(request, "Bus rejected.")
    return redirect("bus_list")

@login_required
def cancel_bus_booking(request, booking_id):
    b = get_object_or_404(BusBooking, id=booking_id)
    is_officer = is_transport_officer(request.user)
    if not (b.requested_by == request.user or is_officer): messages.error(request, "Denied."); return redirect("bus_list")
    if request.method=="POST":
        b.status = BusBooking.STATUS_CANCELLED; b.save()
        if not is_officer: 
            for o in User.objects.filter(groups__name='Transport'): Notification.objects.create(user=o, message=f"CANCELLED: {request.user.username} bus.")
        else:
            Notification.objects.create(user=b.requested_by, message=f"ALERT: Officer cancelled bus to {b.destination}")
            if b.requested_by.email: send_notification_email("Bus Cancelled", "Officer cancelled your bus.", [b.requested_by.email], "bus")
        messages.success(request, "Bus cancelled.")
    return redirect("bus_list")

# === TIMETABLE ===
@user_passes_test(is_dashboard_authorized)
def upload_timetable(request):
    if request.method=="POST":
        sid = request.POST.get("space_id")
        try: day = int(request.POST.get("day_of_week"))
        except: messages.error(request, "Invalid day of week selected."); return redirect("upload_timetable")
        
        if not (0 <= day <= 6):
            messages.error(request, "Invalid day of week selected.")
            return redirect("upload_timetable")

        s, e = parse_date(request.POST.get("sem_start")), parse_date(request.POST.get("sem_end"))
        st = request.POST.get("start_time_custom") or request.POST.get("start_time_select")
        et = request.POST.get("end_time_custom") or request.POST.get("end_time_select")
        
        validations = [
            (not (s and e), "Invalid dates provided."),
            (s and s < timezone.localdate(), "Cannot schedule timetable for past dates."),
            (s and e and s > e, "End date cannot be before start date."),
            (not (st and et), "Start and End times are required."),
            (s and e and (e - s) > timedelta(days=245), "Date range too large. Maximum is 8 months."),
        ]
        for condition, error_msg in validations:
            if condition:
                messages.error(request, error_msg)
                return redirect("upload_timetable")

        space = get_object_or_404(Space, id=sid)
        curr, count, limit = s, 0, 120 # FIX: Increased from 50 to 120
        while curr <= e:
            if curr.weekday() == day:
                if count >= limit:
                    messages.warning(request, f"Safety Limit Reached: Stopped after creating {count} bookings.")
                    break
                if not Booking.objects.filter(space=space, date=curr, status=Booking.STATUS_APPROVED, start_time__lt=et, end_time__gt=st).exists():
                    Booking.objects.create(space=space, requested_by=request.user, date=curr, start_time=st, end_time=et, purpose=f"TIMETABLE: {request.POST.get('subject')}", status=Booking.STATUS_APPROVED, approved_by=request.user, expected_count=request.POST.get("expected_count") or 0)
                    count+=1
            curr+=timedelta(days=1)
        
        if count > 0:
            messages.success(request, f"Created {count} slots for {request.POST.get('subject')}.")
        else:
            messages.info(request, "No bookings were created. Dates may be blocked or outside the selected day of week.")
        return redirect("admin_dashboard")
    return render(request, "upload_timetable.html", {"spaces": Space.objects.all()})

@user_passes_test(is_dashboard_authorized)
def clear_timetable(request):
    if request.method=="POST":
        # FIX: Added .strip() to clean input
        sub = request.POST.get("subject_name", "").strip()
        if not sub: messages.error(request, "Subject req."); return redirect("upload_timetable")
        targets = Booking.objects.filter(purpose__iexact=f"TIMETABLE: {sub}", date__gte=timezone.localdate(), status=Booking.STATUS_APPROVED)
        count = targets.count()
        if count > 0:
            targets.delete()
            messages.success(request, f"Successfully deleted {count} future bookings for '{sub}'.")
        else:
            messages.warning(request, f"No future bookings found for '{sub}'.")
    return redirect("upload_timetable")

# === AUTH ===
def login_view(request):
    if request.user.is_authenticated: return redirect("home")
    form = AuthenticationForm()
    if request.method=="POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user=form.get_user(); login(request, user)
            return redirect('bus_list' if is_transport_officer(user) else (request.POST.get('next') or 'home'))
    return render(request, "login.html", {"form": form})

def logout_view(request): logout(request); return redirect("home")