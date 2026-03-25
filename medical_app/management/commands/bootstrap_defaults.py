from django.core.management.base import BaseCommand

from medical_app.services.bootstrap import bootstrap_defaults


class Command(BaseCommand):
    help = "Ensure default admin credentials and featured home-page records exist."

    def handle(self, *args, **options):
        summary = bootstrap_defaults()
        self.stdout.write(self.style.SUCCESS("Default records synchronized successfully."))
        self.stdout.write(
            "Admin created: {created}, updated: {updated}".format(
                created=summary["admin"]["user_created"],
                updated=summary["admin"]["user_updated"],
            )
        )
        self.stdout.write(
            "Featured images created: {count}".format(
                count=summary["featured_images"]["created"],
            )
        )

