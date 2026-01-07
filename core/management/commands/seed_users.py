import random
from django.core.management.base import BaseCommand
from core.models import CustomUser
from core.auth_utils import hash_user_password

class Command(BaseCommand):
    help = "Seeds random users into the system"

    def handle(self, *args, **options):
        self.stdout.write("Seeding users...")

        # Clear existing users? Maybe strictly adding.
        # CustomUser.objects.all().delete() 

        # 1. Super Admin
        CustomUser.objects.get_or_create(
            email="admin@rajagiri.edu",
            defaults={
                "full_name": "Super Admin",
                "role": CustomUser.SUPER_ADMIN,
                "password": hash_user_password("test@123")
            }
        )

        # 2. Receptionists (2)
        receptionists = [
            ("Lincy Joseph", "lincy@rajagiri.edu"),
            ("Reception Desk", "reception@rajagiri.edu"),
        ]
        for name, email in receptionists:
            CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": name,
                    "role": CustomUser.RECEPTIONIST,
                    "password": hash_user_password("test@123")
                }
            )

        # 3. Faculties (5)
        faculties = [
            ("Dr. Smitha", "smitha@rajagiri.edu"),
            ("Prof. George", "george@rajagiri.edu"),
            ("Dr. Anupama", "anupama@rajagiri.edu"),
            ("Prof. James", "james@rajagiri.edu"),
            ("Dr. Bindu", "bindu@rajagiri.edu"),
        ]
        for name, email in faculties:
            CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": name,
                    "role": CustomUser.FACULTY,
                    "password": hash_user_password("test@123")
                }
            )

        # 4. Students (10)
        first_names = ["Arun", "Babu", "Cyril", "Deepa", "Elsa", "Farhan", "Gokul", "Hari", "Indu", "Jomon"]
        for i, name in enumerate(first_names):
            email = f"{name.lower()}{i+1}@student.rajagiri.edu"
            CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": f"{name} Kumar",
                    "role": CustomUser.STUDENT,
                    "password": hash_user_password("test@123")
                }
            )

        self.stdout.write(self.style.SUCCESS("Successfully seeded users!"))
