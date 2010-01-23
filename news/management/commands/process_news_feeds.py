import datetime
import logging
import os
import time
from optparse import make_option
from django.conf import settings
from django.core.management.base import NoArgsCommand
from django.db.models import Q
from news.decorators import locking
from news.models import Feed, Article

class Command(NoArgsCommand):
    help = "Can be run as a cronjob or directly to download RSS feeds."
    option_list = NoArgsCommand.option_list + (
        make_option(
            '--verbose', action='store_true', dest='verbose',
            help='Log output to console.'
        ),
    )
    @locking
    def handle_noargs(self, **options):
        """
        Update the database with articles
        """
        verbose = options.get('verbose', False)
        logging.basicConfig(
            filename='news_log.log',
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)-8s %(message)s',
        )
        
        if verbose:
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
            console.setFormatter(formatter)
            logging.getLogger('').addHandler(console)

        logging.info('Download starting')
        total_start = time.time()
        new_articles = 0
        
        for feed in Feed.objects.filter(active=True):
            start = time.time()
            logging.info("Downloading: %s..." % feed.url)
            result = feed.download_feed()
            if result == False:
                logging.warn("Error downloading %s" % feed.url)    
            end = time.time()
            logging.info("%d new articles found (took %fs)" % (feed.new_articles_added, end - start))
            new_articles += feed.new_articles_added
            
        total_end = time.time()
        logging.info("Finished processing %d feeds" % Feed.objects.filter(active=True).count())
        logging.info("%d new articles added in %f seconds" % (new_articles, total_end - total_start))
        
        expired_articles = Article.objects.expire_articles()
        logging.info("Expired articles: %s" % expired_articles)
