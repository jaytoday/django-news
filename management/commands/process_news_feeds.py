import datetime
import os
import time
from django.conf import settings
from django.core.management.base import NoArgsCommand
from django.db.models import Q
from djangonews.decorators import locking
from djangonews.models import Feed

class Command(NoArgsCommand):
    help = "Can be run as a cronjob or directly to download user streams and search results from twitter."

    @locking
    def handle_noargs(self, **options):
        """
        Update the database with articles
        """
        total_start = time.time()
        
        for feed in Feed.objects.filter(active=True):
            start = time.time()
            print "Downloading: %s..." % feed.url,
            feed.download_feed()
            print "%d new articles" % feed.new_articles_added
            end = time.time()
            
        total_end = time.time()
        print "-------------------------"
        print "Done: (took %fs)" % (total_end - total_start)
