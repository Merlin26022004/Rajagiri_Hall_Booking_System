from django.core.management.base import BaseCommand
from core.models import Hall

class Command(BaseCommand):
    help = "Seeds halls into the system"

    def handle(self, *args, **options):
        self.stdout.write("Seeding halls...")

        halls_data = [
            {
                "name": "Golden Aureole Hall",
                "seating_capacity": 180,
                "facilities": "AC, Stage, Podium Mic, Cordless Mic (1), Wired Mic (1), Projector, Sound System",
                "image_path": "halls/golden_aureole.jpg"
            },
            {
                "name": "Alex Hall",
                "seating_capacity": 60,
                "facilities": "AC, Panel, Podium Mic, Wired Mic, Wireless Mic, Projector, Sound System",
                "image_path": "halls/alex_hall.jpg"
            },
            {
                "name": "Carmel Hall",
                "seating_capacity": 130,
                "facilities": "AC, Panel, Projector, Podium Mic, Wired Mic, Wireless Mics (2), Collar Mic",
                "image_path": "halls/carmel_hall.jpg"
            },
            {
                "name": "Chavara Hall",
                "seating_capacity": 200,
                "facilities": "Projector, Wired Mic, Cordless Mic",
                "image_path": "halls/chavara_hall.jpg"
            },
            {
                "name": "Board Room – 1",
                "seating_capacity": 15,
                "facilities": "AC, Panel",
                "image_path": "halls/boardroom1.jpg"
            },
            {
                "name": "Board Room – 2",
                "seating_capacity": 8, # Approx for Small
                "facilities": "AC, Projector",
                "image_path": "halls/boardroom2.jpg"
            },
            {
                "name": "Parlour",
                "seating_capacity": 10,
                "facilities": "AC",
                "image_path": "halls/parlour.jpg"
            },
            {
                "name": "Gyan Prayag (Cabins)",
                "seating_capacity": 3, # Units: 3 cabins. Storing as approx total capacity or handling specially? Storing 3.
                "facilities": "Cabin-style rooms (3 Units)",
                "image_path": "halls/gyan_prayag.jpg"
            },
        ]

        for hall_data in halls_data:
            Hall.objects.get_or_create(
                name=hall_data["name"],
                defaults={
                    "seating_capacity": hall_data["seating_capacity"],
                    "facilities": hall_data["facilities"],
                    "image_path": hall_data["image_path"],
                    "description": f"Standard description for {hall_data['name']}. Ideally this should be more detailed.",
                    "typical_use_cases": "Lectures, Meetings, Events",
                    "booking_considerations": "Please book 2 days in advance."
                }
            )

        self.stdout.write(self.style.SUCCESS("Successfully seeded halls!"))
