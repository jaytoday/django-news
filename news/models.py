import time
import datetime
import feedparser
import re

from django.conf import settings
from django.db import models

BLOCKED_HTML = getattr(settings, 'NEWS_BLOCKED_HTML', [])
BLOCKED_REGEX = re.compile(r'<(%s)[^>]*(/>|.*?</\1>)' % ('|'.join(BLOCKED_HTML)), re.DOTALL | re.IGNORECASE)

class Source(models.Model):
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
    keywords = models.TextField(help_text="Comma separated list of keywords to check")
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s' % self.name

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, default=None,
        related_name='children', verbose_name='Parent')
    
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
            self.level = self.parent.level + 1
            url_path = '%s%s/' % (self.parent.url_path, self.slug)
        else:
            self.level = 0
            url_path = '%s/' % (self.slug)
 
        self.url_path = url_path
        
        super(Category, self).save(*args, **kwargs)
                
        Category.objects.filter(pk=self.pk).update(
            url_path=self.url_path
        )
        
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

class Feed(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField()
    categories = models.ManyToManyField(Category, through='FeedCategoryRelationship')
    source = models.ForeignKey(Source)
    last_download = models.DateField(auto_now=True)
    new_articles_added = models.PositiveSmallIntegerField(default=0, editable=False)
    active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s - %s' % (self.source.name, self.name)
    
    def download_feed(self):
        try:
            data = feedparser.parse(self.url)
        except:
            return False
        
        new_articles_added = 0
        
        for entry in data.entries:
            entry.title = re.sub('<[^>]*>', '', entry.title) # remove all tags from title
            headline = entry.title.encode(data.encoding, "xmlcharrefreplace")
            guid = entry.get("id", entry.link).encode(data.encoding, "xmlcharrefreplace")
            url = entry.link.encode(data.encoding, "xmlcharrefreplace")

            if not guid:
                guid = url

            try:
                article = Article.objects.get(guid=guid, feed=self)
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
                
                article = Article(
                    feed=self,
                    headline=headline, 
                    url=url, 
                    content=content, 
                    guid=guid, 
                    publish=date_modified
                )
                
            add_to_categories = []
            
            for category in self.categories.all():
                relationship_queryset = FeedCategoryRelationship.objects.filter(feed=self, category=category)
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
                article.categories = add_to_categories
                article.save()
        
        self.new_articles_added = new_articles_added
        self.last_downloaded = datetime.datetime.now()
        self.save()

class FeedCategoryRelationship(models.Model):
    feed = models.ForeignKey(Feed)
    category = models.ForeignKey(Category)
    white_list = models.ManyToManyField(WhiteListFilter, blank=True)

class Article(models.Model):
    headline = models.CharField(max_length=255)
    slug = models.SlugField()
    publish = models.DateTimeField(default=datetime.datetime.now)
    url = models.URLField()
    content = models.TextField()
    guid = models.CharField(max_length=255, blank=True, editable=False)
    
    feed = models.ForeignKey(Feed, related_name='articles')
    categories = models.ManyToManyField(Category, related_name='articles')
    
    class Meta:
        ordering = ('-publish', 'headline')
    
    def __unicode__(self):
        return u'%s' % self.headline
    
    def get_absolute_url(self):
        return self.url
