import json
from datetime import timedelta, time, date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.core import mail
from unittest.mock import patch

# Adjust imports based on your app name
from core.models import Space, Booking, Bus, BusBooking, BlockedDate, Notification, Facility

class CoreSystemTests(TestCase):

    def setUp(self):
        # 1. Setup Client
        self.client = Client()

        # 2. Setup Groups
        self.admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.transport_group, _ = Group.objects.get_or_create(name='Transport')
        self.faculty_group, _ = Group.objects.get_or_create(name='Faculty')
        # CRITICAL FIX: Create a generic group so student isn't stuck in "Waiting" status
        self.student_group, _ = Group.objects.get_or_create(name='Student Rep') 

        # 3. Setup Users
        self.superuser = User.objects.create_superuser('admin', 'admin@test.com', 'password')
        
        self.transport_officer = User.objects.create_user('officer', 'officer@test.com', 'password')
        self.transport_officer.groups.add(self.transport_group)

        self.faculty_user = User.objects.create_user('faculty', 'faculty@test.com', 'password')
        self.faculty_user.groups.add(self.faculty_group)

        self.student_user = User.objects.create_user('student', 'student@test.com', 'password')
        # CRITICAL FIX: Add student to a group to bypass @approval_required
        self.student_user.groups.add(self.student_group)

        # 4. Setup Resources
        self.space = Space.objects.create(name="Auditorium", capacity=100)
        self.facility = Facility.objects.create(name="Projector")
        self.space.facilities.add(self.facility)
        
        self.bus = Bus.objects.create(number_plate="KL-07-1234", capacity=40)

    # ==========================================
    # 1. BUS BOOKING FLOW TESTS
    # ==========================================

    def test_bus_booking_lifecycle(self):
        """
        Test the full lifecycle: Book -> Approve -> Cancel
        """
        self.client.login(username='student', password='password')
        
        # 1. Book a Bus
        future_date = timezone.localdate() + timedelta(days=2)
        response = self.client.post(reverse('book_bus'), {
            'bus_id': self.bus.id,
            'date': future_date,
            'start_time': '09:00',
            'end_time': '12:00',
            'origin': 'Campus',
            'destination': 'Industrial Visit',
            'purpose': 'Study Tour'
        })
        
        # This check failed previously because user was unapproved (200 OK)
        # Now it should be 302 (Redirect to list)
        self.assertEqual(response.status_code, 302) 
        
        booking = BusBooking.objects.first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.status, 'Pending')

        # 2. Transport Officer Approves
        self.client.login(username='officer', password='password')
        # Note: ensuring we use the updated view logic (booking_id)
        response = self.client.post(reverse('approve_bus_booking', args=[booking.id]))
        
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Approved')
        # Check Notification
        self.assertTrue(Notification.objects.filter(user=self.student_user, message__contains="BUS APPROVED").exists())

        # 3. Transport Officer Rejects (Separate logic check)
        # Reset status for test
        booking.status = 'Pending'
        booking.save()
        response = self.client.post(reverse('reject_bus_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Rejected')

    def test_bus_cancellation_permissions(self):
        """
        Test that only the owner or transport officer can cancel.
        """
        # Create booking by student
        booking = BusBooking.objects.create(
            bus=self.bus, requested_by=self.student_user, date=timezone.localdate(),
            start_time='10:00', end_time='11:00', origin='A', destination='B'
        )

        # Login as random faculty (unrelated user)
        self.client.login(username='faculty', password='password')
        response = self.client.post(reverse('cancel_bus_booking', args=[booking.id]))
        # Should fail (redirect with error or permission denied)
        # Assuming view redirects on error:
        self.assertEqual(response.status_code, 302) 
        
        booking.refresh_from_db()
        # Status should NOT be cancelled
        self.assertNotEqual(booking.status, BusBooking.STATUS_CANCELLED)

        # Login as Officer (Should succeed)
        self.client.login(username='officer', password='password')
        response = self.client.post(reverse('cancel_bus_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BusBooking.STATUS_CANCELLED)

    # ==========================================
    # 2. QUEUE & PROMOTION LOGIC TESTS
    # ==========================================

    def test_admin_rejection_promotes_waitlisted(self):
        """
        If Admin rejects the 'blocking' PENDING user, the Waitlisted user should be promoted.
        """
        tomorrow = timezone.localdate() + timedelta(days=1)
        
        # User A (Pending)
        booking_a = Booking.objects.create(
            space=self.space, requested_by=self.student_user, 
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_PENDING, purpose="User A", expected_count=10
        )

        # User B (Waitlisted) - Exact same time
        booking_b = Booking.objects.create(
            space=self.space, requested_by=self.faculty_user, 
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_WAITLISTED, purpose="User B", expected_count=10
        )

        # Admin Rejects A
        self.client.login(username='admin', password='password')
        self.client.post(reverse('reject_booking', args=[booking_a.id]))

        # Check A is Rejected
        booking_a.refresh_from_db()
        self.assertEqual(booking_a.status, Booking.STATUS_REJECTED)

        # Check B is Promoted
        booking_b.refresh_from_db()
        self.assertEqual(booking_b.status, Booking.STATUS_PENDING)
        self.assertIsNotNone(booking_b.approval_deadline) 

    def test_admin_approval_notifies_waitlisted(self):
        """
        If Admin approves the 'blocking' user, Waitlisted users are NOT rejected,
        but notified they are on Standby.
        """
        tomorrow = timezone.localdate() + timedelta(days=1)
        
        booking_a = Booking.objects.create(
            space=self.space, requested_by=self.student_user, 
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_PENDING, purpose="User A", expected_count=10
        )

        booking_b = Booking.objects.create(
            space=self.space, requested_by=self.faculty_user, 
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_WAITLISTED, purpose="User B", expected_count=10
        )

        # Admin Approves A
        self.client.login(username='admin', password='password')
        self.client.post(reverse('approve_booking', args=[booking_a.id]))

        # Check B is still Waitlisted (Standby)
        booking_b.refresh_from_db()
        self.assertEqual(booking_b.status, Booking.STATUS_WAITLISTED)

        # Check Notification for B
        notif_exists = Notification.objects.filter(
            user=self.faculty_user, 
            message__contains="Standby"
        ).exists()
        self.assertTrue(notif_exists)

    def test_queue_position_property(self):
        """
        Test the queue_position property logic on the Model.
        """
        tomorrow = timezone.localdate() + timedelta(days=1)
        
        # 1. Approved Booking (Blocking)
        Booking.objects.create(
            space=self.space, requested_by=self.student_user,
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_APPROVED, expected_count=10
        )

        # 2. First Waitlist
        wl_1 = Booking.objects.create(
            space=self.space, requested_by=self.faculty_user,
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_WAITLISTED, expected_count=10
        )

        # 3. Second Waitlist
        wl_2 = Booking.objects.create(
            space=self.space, requested_by=self.transport_officer,
            date=tomorrow, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_WAITLISTED, expected_count=10
        )

        # Check Positions
        self.assertEqual(wl_1.queue_position, 1)
        self.assertEqual(wl_2.queue_position, 2)

    # ==========================================
    # 3. TIMETABLE LOGIC TESTS
    # ==========================================

    def test_timetable_duration_cap(self):
        """
        Test that timetable upload fails if range > 8 months.
        """
        self.client.login(username='admin', password='password')
        
        start_date = timezone.localdate()
        end_date = start_date + timedelta(days=300) # > 8 months

        response = self.client.post(reverse('upload_timetable'), {
            'space_id': self.space.id,
            'day_of_week': start_date.weekday(),
            'sem_start': start_date,
            'sem_end': end_date,
            'start_time_custom': '09:00',
            'end_time_custom': '10:00',
            'subject': 'Physics',
            'expected_count': 50
        })

        # Should fail and redirect back with error
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("Date range too large" in str(m) for m in messages))
        
        self.assertEqual(Booking.objects.count(), 0)

    def test_timetable_success(self):
        """
        Test valid timetable upload.
        """
        self.client.login(username='admin', password='password')
        
        start_date = timezone.localdate()
        # Find next Monday (0)
        days_ahead = 0 - start_date.weekday()
        if days_ahead <= 0: days_ahead += 7
        next_monday = start_date + timedelta(days=days_ahead)
        
        response = self.client.post(reverse('upload_timetable'), {
            'space_id': self.space.id,
            'day_of_week': 0, # Monday
            'sem_start': next_monday,
            'sem_end': next_monday + timedelta(days=14), # 3 weeks cover
            'start_time_custom': '09:00',
            'end_time_custom': '10:00',
            'subject': 'Maths',
            'expected_count': 50
        })

        # Should succeed
        self.assertEqual(Booking.objects.filter(purpose="TIMETABLE: Maths").count(), 3)

    def test_clear_timetable_validation(self):
        """
        Test clearing timetable requires subject and actually deletes.
        """
        self.client.login(username='admin', password='password')
        
        # Create dummy timetable bookings
        Booking.objects.create(
            space=self.space, requested_by=self.superuser,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(9,0), end_time=time(10,0),
            purpose="TIMETABLE: Chemistry", status=Booking.STATUS_APPROVED, expected_count=50
        )

        # 1. Try to clear without subject
        response = self.client.post(reverse('clear_timetable'), {})
        self.assertEqual(Booking.objects.count(), 1) # Should not delete

        # 2. Clear with subject
        response = self.client.post(reverse('clear_timetable'), {'subject_name': 'Chemistry'})
        self.assertEqual(Booking.objects.count(), 0) # Should delete

    # ==========================================
    # 4. API ENDPOINT TESTS
    # ==========================================

    def test_api_unavailable_dates(self):
        self.client.login(username='student', password='password')
        
        # Block a date
        block_date = timezone.localdate() + timedelta(days=5)
        BlockedDate.objects.create(space=self.space, date=block_date, reason="Holiday")

        response = self.client.get(reverse('api_unavailable_dates'), {'space_id': self.space.id})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn(block_date.isoformat(), data)

    def test_space_day_slots(self):
        self.client.login(username='student', password='password')
        target_date = timezone.localdate() + timedelta(days=1)

        # Create Approved Booking
        Booking.objects.create(
            space=self.space, requested_by=self.student_user,
            date=target_date, start_time=time(10,0), end_time=time(12,0),
            status=Booking.STATUS_APPROVED, expected_count=10
        )

        response = self.client.get(reverse('space_day_slots'), {'space_id': self.space.id, 'date': target_date})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # Should return start/end of the approved booking
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['start'], '10:00:00')
        self.assertEqual(data[0]['end'], '12:00:00')

    def test_api_space_facilities(self):
        self.client.login(username='student', password='password')
        response = self.client.get(reverse('api_space_facilities'), {'space_id': self.space.id})
        data = json.loads(response.content)
        self.assertEqual(data[0]['name'], 'Projector')

    # ==========================================
    # 5. DASHBOARD & PERMISSIONS
    # ==========================================
    
    def test_dashboard_access_control(self):
        # Student -> Fail (Redirect to login/home because only Admin/Faculty allowed)
        self.client.login(username='student', password='password')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302) 

        # Admin -> Success
        self.client.login(username='admin', password='password')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)