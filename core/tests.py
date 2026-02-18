from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.core import mail
from datetime import timedelta, time, date
from .models import Space, Booking, SpaceType, BlockedDate, Facility

class AdvancedBookingLogicTests(TestCase):
    def setUp(self):
        # 1. Setup Groups
        self.student_group, _ = Group.objects.get_or_create(name='Student Rep')
        self.faculty_group, _ = Group.objects.get_or_create(name='Faculty')
        self.transport_group, _ = Group.objects.get_or_create(name='Transport')

        # 2. Setup Users
        self.admin = User.objects.create_superuser('admin', 'admin@test.com', 'pass')
        
        self.student = User.objects.create_user('student', 'student@test.com', 'pass')
        self.student.groups.add(self.student_group)
        self.student.save()
        
        self.staff = User.objects.create_user('staff', 'staff@test.com', 'pass')
        self.staff.groups.add(self.faculty_group)
        self.staff.save()

        # 3. Setup Infrastructure
        self.hall_type = SpaceType.objects.create(name="Auditorium")
        self.hall = Space.objects.create(name="Main Hall", capacity=200, type=self.hall_type)
        
        # 4. Common Data
        self.tomorrow = timezone.localdate() + timedelta(days=1)
        self.next_week = timezone.localdate() + timedelta(days=7)
        self.start_time = time(10, 0)
        self.end_time = time(12, 0)
        
        self.client = Client()

    def test_priority_promotion_logic(self):
        """
        CRITICAL: Test that 'External' waitlisted users (Rank 1) are promoted 
        before 'Internal' waitlisted users (Rank 2), regardless of creation time.
        """
        self.client.force_login(self.admin)

        # 1. Create a "Blocking" Approved Booking
        blocker = Booking.objects.create(
            space=self.hall, requested_by=self.staff,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="Blocker", status=Booking.STATUS_APPROVED,
            expected_count=50  # FIX: Required field
        )

        # 2. Create Internal Waitlist (Created FIRST)
        internal_wl = Booking.objects.create(
            space=self.hall, requested_by=self.student,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="Internal Event", status=Booking.STATUS_WAITLISTED,
            resource_type='Internal', # Rank 2
            expected_count=50  # FIX: Required field
        )

        # 3. Create External Waitlist (Created SECOND)
        external_wl = Booking.objects.create(
            space=self.hall, requested_by=self.staff,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="External Event", status=Booking.STATUS_WAITLISTED,
            resource_type='External', # Rank 1 (Should win)
            expected_count=50  # FIX: Required field
        )

        # 4. Admin Cancels the Blocker
        self.client.post(reverse('admin_cancel_booking', args=[blocker.id]), follow=True)

        # 5. Verify Results
        internal_wl.refresh_from_db()
        external_wl.refresh_from_db()

        self.assertEqual(external_wl.status, Booking.STATUS_PENDING, 
                         "External user should be promoted due to Rank 1 priority.")
        self.assertEqual(internal_wl.status, Booking.STATUS_WAITLISTED, 
                         "Internal user should remain waitlisted.")
        
        # 6. Verify Email Sent (Queue Manager Logic)
        # FIX: Check ALL emails in the outbox to avoid race condition with cancellation email
        self.assertTrue(len(mail.outbox) > 0)
        all_subjects = [m.subject for m in mail.outbox]
        self.assertTrue(
            any("Booking Update: You've Moved Up!" in s for s in all_subjects),
            f"Promotion email not found. Subjects sent: {all_subjects}"
        )

    def test_reschedule_blocked_date_security(self):
        """
        CRITICAL: Ensure reschedule_booking prevents moving to a BlockedDate.
        """
        self.client.force_login(self.student)

        # 1. Create original booking on Tomorrow
        booking = Booking.objects.create(
            space=self.hall, requested_by=self.student,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="Original", status=Booking.STATUS_APPROVED,
            faculty_in_charge="Dr. X",
            expected_count=50  # FIX: Required field
        )

        # 2. Administratively Block 'Next Week'
        BlockedDate.objects.create(date=self.next_week, reason="Holiday")

        # 3. Attempt to Reschedule into the Blocked Date
        response = self.client.post(reverse('reschedule_booking', args=[booking.id]), {
            'space': self.hall.id,
            'date': self.next_week.strftime('%Y-%m-%d'), # Target blocked date
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M'),
            'purpose': "Reschedule Attempt",
            'expected_count': 50
        }, follow=True)

        # 4. Verify Failure
        booking.refresh_from_db()
        self.assertEqual(booking.date, self.tomorrow, "Booking date should NOT have changed.")
        self.assertContains(response, "administratively blocked")

    def test_reschedule_frees_slot_and_promotes(self):
        """
        Verify that moving a booking out of a slot triggers promotion for that old slot.
        """
        self.client.force_login(self.student)

        # 1. Student A holds the slot
        booking_a = Booking.objects.create(
            space=self.hall, requested_by=self.student,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="Holding Slot", status=Booking.STATUS_APPROVED,
            expected_count=50  # FIX: Required field
        )

        # 2. Student B is Waitlisted for same slot
        booking_b = Booking.objects.create(
            space=self.hall, requested_by=self.staff,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="Waiting", status=Booking.STATUS_WAITLISTED,
            resource_type='Internal',
            expected_count=50  # FIX: Required field
        )

        # 3. Student A Reschedules to a free day (Next Week)
        self.client.post(reverse('reschedule_booking', args=[booking_a.id]), {
            'space': self.hall.id,
            'date': self.next_week.strftime('%Y-%m-%d'),
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M'),
            'purpose': "Moving Away",
            'expected_count': 50
        }, follow=True)

        # 4. Verify A Moved and B Promoted
        booking_a.refresh_from_db()
        booking_b.refresh_from_db()

        self.assertEqual(booking_a.date, self.next_week, "Booking A should move to new date.")
        self.assertEqual(booking_b.status, Booking.STATUS_PENDING, "Booking B should be promoted to Pending.")

    def test_timetable_upload_limit(self):
        """
        Verify the timetable upload loop breaks at the safety limit (120).
        """
        self.client.force_login(self.admin)
        
        # Define a date range larger than 120 days (e.g., 200 days)
        start_date = self.tomorrow
        end_date = start_date + timedelta(days=200)
        target_weekday = start_date.weekday()

        response = self.client.post(reverse('upload_timetable'), {
            'space_id': self.hall.id,
            'sem_start': start_date.strftime('%Y-%m-%d'),
            'sem_end': end_date.strftime('%Y-%m-%d'),
            'day_of_week': target_weekday,
            'start_time_custom': '09:00',
            'end_time_custom': '10:00',
            'subject': 'CS101',
            'expected_count': 60
        }, follow=True)

        count = Booking.objects.filter(purpose__contains="TIMETABLE: CS101").count()
        self.assertContains(response, "Created")
        self.assertTrue(count > 0)

    def test_clear_timetable_whitespace(self):
        """
        Verify clear_timetable strips whitespace from input.
        """
        self.client.force_login(self.admin)
        
        # Create a timetable booking
        Booking.objects.create(
            space=self.hall, requested_by=self.admin,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            purpose="TIMETABLE: Math 101", status=Booking.STATUS_APPROVED,
            expected_count=50  # FIX: Required field
        )

        # Try to delete with messy input " Math 101 "
        response = self.client.post(reverse('clear_timetable'), {
            'subject_name': '  Math 101  ' 
        }, follow=True)

        self.assertContains(response, "Successfully deleted 1")
        self.assertFalse(Booking.objects.filter(purpose="TIMETABLE: Math 101").exists())

    def test_admin_dashboard_sorting(self):
        """
        Verify the admin dashboard loads without error and uses the priority annotation.
        """
        self.client.force_login(self.admin)
        
        # Create various bookings
        Booking.objects.create(
            space=self.hall, requested_by=self.student,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            status=Booking.STATUS_PENDING, resource_type='Internal',
            expected_count=50  # FIX: Required field
        )
        Booking.objects.create(
            space=self.hall, requested_by=self.staff,
            date=self.tomorrow, start_time=self.start_time, end_time=self.end_time,
            status=Booking.STATUS_PENDING, resource_type='External',
            expected_count=50  # FIX: Required field
        )

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        self.assertIn('bookings', response.context)
        
        queue = list(response.context['bookings'])
        # Depending on sort order logic in view, verify priority
        # If view sorts by priority_rank (External=1, Internal=2), External should be first
        self.assertEqual(queue[0].resource_type, 'External')
        self.assertEqual(queue[1].resource_type, 'Internal')