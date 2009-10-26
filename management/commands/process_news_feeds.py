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
        Update the database with new tweets from various sources
        
        1. Users
            - Staff accounts can be configured in the admin and these
            will be updated every time the command is run.
            - In some instances, a non-staff account may need to be updated,
            if for instance, that account is a part of a "TwitterGroup".  In
            these cases, the account's user stream will be updated if one of
            the following is true:
                - It has been requested and was last updated some time before
                  now() - cache_timeout (default is 10 minutes ago)
                - The last time it was fetched there were several new tweets,
                  indicating this is an active stream (TWITTER_NEW_TWEETS_THRESHOLD)
        2. Searches
            - Searches are configured in the admin and are updated similarly
            to Users.  If a search is flagged to update continuously (i.e. #lawrence)
            it will update every time the command is run.
            - For other searches, which may be more time-sensitive (related to a news
            item and included as a story inline), the search results will be updated
            the same way Users are:
                - It has been requested and was last updated some time before
                  now() - cache_timeout (default is 10 minutes ago)
                - The last time it was fetched there were several new tweets,
                  indicating this is an active search (TWITTER_NEW_TWEETS_THRESHOLD)
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
