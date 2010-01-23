import time
import datetime
import feedparser
import re

from django.conf import settings
from django.db import models

# blocked html takes a list of tag names, i.e. ['script', 'img', 'embed']
BLOCKED_HTML = getattr(settings, 'NEWS_BLOCKED_HTML', [])
BLOCKED_REGEX = re.compile(r'<(%s)[^>]*(/>|.*?</\1>)' % ('|'.join(BLOCKED_HTML)), 
                           re.DOTALL | re.IGNORECASE)

# number of days after which articles should be marked expired
EXPIRE_ARTICLES = getattr(settings, 'EXPIRE_ARTICLES', True)
EXPIRE_ARTICLES_DAYS = getattr(settings, 'EXPIRE_ARTICLES', 7)

class Source(models.Model):
    """
    A source is a general news source, like CNN, who may provide multiple feeds.
    """
    name = models.CharField(max_length=255)
    url = models.URLField()
    description = models.TextField(blank=True)
    logo = models.ImageField(blank=True, upload_to='images/news_logos')
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s' % self.name

class WhiteListFilter(models.Model):
    name = models.CharField(max_length=50)
    keywords = models.TextField(help_text="Comma separated list of keywords")
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s' % self.name

class Category(models.Model):
    """
    Categories are populated by collections of feeds and/or other categories.
    They can be configured in a heirarchy, like
    
    /news/sports/basketball/
    
    When feeds are processed, each feed checks to see what categories it can go
    into, and additionally, what white-list filters to apply before adding the
    articles to that category.
    """
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, default=None,
        related_name='children', verbose_name='Parent')
    
    # allow categories to include articles from other categories
    include_categories = models.ManyToManyField('self', symmetrical=False,
        through='CategoryRelationship', related_name='including_categories')
    
    # cached field, updated on save
    url_path = models.CharField(max_length=255, editable=False, db_index=True)
    level = models.IntegerField(default=0, editable=False)
    
    class Meta:
        verbose_name_plural = 'categories'
        ordering = ('url_path',)

    def __unicode__(self):
        return u'%s' % self.url_path
    
    def save(self, *args, **kwargs):
        if self.parent:
            # denormalize a path to this category and store its depth
            self.level = self.parent.level + 1
            url_path = '%s%s/' % (self.parent.url_path, self.slug)
        else:
            self.level = 0
            url_path = '%s/' % (self.slug)
 
        self.url_path = url_path
        
        super(Category, self).save(*args, **kwargs)
        
        # update all subcategories in case the url_path changed
        if self.children:
            def update_children(children):
                for child in children:
                    child.save()
                    if child.children:
                        update_children(child.children.all())
            update_children(self.children.all())

    @models.permalink
    def get_absolute_url(self):
        return ('news_article_index', None, { 'url_path': self.url_path })


class CategoryRelationship(models.Model):
    """
    Allow a category to include articles from other categories, optionally
    filtering the incoming articles with a white-list.  This operation happens
    when a feed is downloaded, and so only applies to articles going forward
    from the time the relationship is established.
    """
    category = models.ForeignKey(Category, related_name='categories')
    included_category = models.ForeignKey(Category, 
        related_name='included_categories')
    white_list = models.ManyToManyField(WhiteListFilter, blank=True)
    

class Feed(models.Model):
    """
    A feed is the actual RSS/Atom feed that will be downloaded.  It has a
    many-to-many relationship to categories through the FeedCategoryRelationship
    model, which allows white-lists to be applied to the feed before articles
    will be added to the category.
    """
    name = models.CharField(max_length=255)
    url = models.URLField()
    categories = models.ManyToManyField(Category, 
        through='FeedCategoryRelationship')
    source = models.ForeignKey(Source)
    last_download = models.DateField(auto_now=True)
    new_articles_added = models.PositiveSmallIntegerField(default=0, 
        editable=False)
    active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s - %s' % (self.source.name, self.name)
    
    def download_feed(self):
        try:
            # download the feed data
            data = feedparser.parse(self.url)
        except:
            return False
        
        new_articles_added = 0
        
        # iterate over the entries returned by the feed
        for entry in data.entries:
            # remove all HTML from the title and clean up the data
            entry.title = re.sub('<[^>]*>', '', entry.title)
            headline = entry.title.encode(data.encoding, "xmlcharrefreplace")
            guid = entry.get("id", entry.link).encode(data.encoding, "xmlcharrefreplace")
            url = entry.link.encode(data.encoding, "xmlcharrefreplace")
            
            if not guid:
                guid = url
            
            try:
                article = Article.objects.get(
                    models.Q(guid=guid, feed=self) |
                    models.Q(headline__iexact=headline))
            except Article.DoesNotExist:
                if hasattr(entry, "summary"):
                    content = entry.summary
                elif hasattr(entry, "content"):
                    content = entry.content[0].value
                elif hasattr(entry, "description"):
                    content = entry.description
                else:
                    content = u""
                content = content.encode(data.encoding, "xmlcharrefreplace")
                
                try:
                    pubdate = None
                    attrs = ['updated_parsed', 'published_parsed', 'date_parsed', 'created_parsed']
                    for attr in attrs:
                        if hasattr(entry, attr):
                            pubdate = getattr(entry, attr)
                            break
                    
                    if not pubdate:
                        if data.feed.has_key('updated_parsed'):
                            pubdate = data.feed.updated_parsed
                        elif data.feed.has_key('updated'):
                            pubdate = data.feed.updated
                    
                    if pubdate:
                        date_modified = datetime.datetime.fromtimestamp(time.mktime(pubdate))
                    else:
                        date_modified = datetime.datetime.now()
                except TypeError:
                    date_modified = datetime.datetime.now()
                
                # note: the article is not getting saved yet - only save those
                # articles that will go into at least one category
                article = Article(
                    feed=self,
                    headline=headline, 
                    url=url, 
                    content=content, 
                    guid=guid, 
                    publish=date_modified
                )
            
            # what categories will this article get added to?    
            add_to_categories = []
            
            # iterate over the categories associated with this feed
            for category in self.categories.all():
                relationship_queryset = FeedCategoryRelationship.objects.filter(
                    feed=self, category=category)
                article_passes = True
                
                for relationship in relationship_queryset.all():
                    whitelist = []
                    for white_list in relationship.white_list.all():
                        whitelist += white_list.keywords.split(',')
                    
                    if whitelist:
                        if not re.search(re.compile(r'(%s)' % '|'.join([s.strip() for s in whitelist if s.strip()]), re.IGNORECASE), article.headline):
                            article_passes = False
                            break
                    
                    if BLOCKED_HTML:
                        article.content = re.sub(BLOCKED_REGEX, '', article.content)
                    
                if article_passes:
                    add_to_categories.append(category)
            
            if len(add_to_categories) > 0:
                if not article.pk:
                    new_articles_added += 1
                article.save()
                
                # now check the categories we're adding the article to, and see
                # if any other categories include them - if so, make sure the
                # article passes any white-lists and add the article to the
                # included categories as well
                for category in add_to_categories:
                    for category_relationship in CategoryRelationship.objects.filter(included_category=category):
                        article_passes = True
                        whitelist = []
                        for white_list in category_relationship.white_list.all():
                            whitelist += white_list.keywords.split(',')
                        
                        if whitelist:
                            if not re.search(re.compile(r'(%s)' % '|'.join([s.strip() for s in whitelist if s.strip()]), re.IGNORECASE), article.headline):
                                article_passes = False
                                break
                        
                        add_to_categories.append(category_relationship.category)
                
                article.categories = add_to_categories
                article.save()
        
        self.new_articles_added = new_articles_added
        self.last_downloaded = datetime.datetime.now()
        self.save()

class FeedCategoryRelationship(models.Model):
    feed = models.ForeignKey(Feed)
    category = models.ForeignKey(Category)
    white_list = models.ManyToManyField(WhiteListFilter, blank=True)


class ArticleManager(models.Manager):
    def expire_articles(self):
        if EXPIRE_ARTICLES:
            expire_date = datetime.datetime.now() - datetime.timedelta(
                days=EXPIRE_ARTICLES_DAYS)
            num_expired = self.filter(date_added__lt=expire_date).update(
                expired=True)
            return num_expired

class Article(models.Model):
    headline = models.CharField(max_length=255)
    slug = models.SlugField()
    publish = models.DateTimeField(default=datetime.datetime.now)
    url = models.URLField()
    content = models.TextField()
    guid = models.CharField(max_length=255, blank=True, editable=False)
    date_added = models.DateTimeField(auto_now_add=True)
    expired = models.BooleanField(default=False)
    
    feed = models.ForeignKey(Feed, related_name='articles')
    categories = models.ManyToManyField(Category, related_name='articles')
    
    objects = ArticleManager()
    
    class Meta:
        ordering = ('-publish', 'headline')
    
    def __unicode__(self):
        return u'%s' % self.headline
    
    def get_absolute_url(self):
        return self.url
