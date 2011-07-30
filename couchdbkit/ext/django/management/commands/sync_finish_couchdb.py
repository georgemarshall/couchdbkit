from django.core.management.base import NoArgsCommand
from django.db.models import get_apps

from couchdbkit.ext.django.loading import couchdbkit_handler

class Command(NoArgsCommand):
    help = 'Copy temporary design docs over existing ones'

    def handle_noargs(self, **options):
        for app in get_apps():
            couchdbkit_handler.copy_designs(app, temp='tmp', verbosity=2)
