from django.core.management.base import NoArgsCommand
from django.db.models import get_apps

from couchdbkit.ext.django.loading import couchdbkit_handler

class Command(NoArgsCommand):
    help = 'Sync design docs to temporary ids'

    def handle_noargs(self, **options):
        for app in get_apps():
            couchdbkit_handler.sync(app, verbosity=2, temp='tmp')
