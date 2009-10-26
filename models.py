import time
import datetime
import feedparser
import re
from django.conf import settings
from django.db import models

LOGO_DIMENSIONS = getattr(settings, 'NEWS_LOGO_DIMENSIONS', (48, 48))

DEFAULT_ALLOWED_HTML = getattr(settings, 'NEWS_DEFAULT_ALLOWED_HTML', ['p', 'a', 'ul', 'li', 'blockquote'])
DEFAULT_BLOCKED_HTML = getattr(settings, 'NEWS_DEFAULT_BLOCKED_HTML', [])

ALLOWED_REGEX = re.compile(r'<(%s)[^>]*(/>|.*?</\1>)' % ('|'.join(DEFAULT_ALLOWED_HTML)), re.DOTALL | re.IGNORECASE)
BLOCKED_REGEX = re.compile(r'<((?!%s))[^>]*(/>|.*?</.*?>)' % ('|'.join(DEFAULT_ALLOWED_HTML)), re.DOTALL | re.IGNORECASE)

class Source(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField()
    description = models.TextField(blank=True)
    logo = models.ImageField(blank=True, upload_to='news_logos')
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s' % self.name

class KeywordFilter(models.Model):
    name = models.CharField(max_length=50)
    keywords = models.TextField(help_text="Comma separated list of keywords to check")
    
    class Meta:
        ordering = ('name',)
    
    def __unicode__(self):
        return u'%s' % self.name

class WhiteListFilter(KeywordFilter):
    pass

class BlackListFilter(KeywordFilter):
    pass

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, default=None,
        related_name='children', verbose_name='Parent')
    
    # cached field, updated on save
    url_path = models.CharField(max_length=255, editable=False, db_index=True)
    
    class Meta:
        verbose_name_plural = 'categories'
        ordering = ('url_path',)

    def __unicode__(self):
        return u'%s' % self.url_path
    
    def save(self, *args, **kwargs):
        super(Category, self).save(*args, **kwargs)
        
        if self.parent:
            url_path = '%s%s/' % (self.parent.url_path, self.slug)
        else:
            url_path = '%s/' % (self.slug)
 
        self.url_path = url_path
        
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
        return ('djangonews_article_index', None, { 'url_path': self.url_path })

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
        data = feedparser.parse(self.url)
        new_articles_added = 0
        
        for entry in data.entries:
            entry.title = re.sub('<[^>]*>', '', entry.title) # remove all tags from title
            try:
                article = Article.objects.get(headline__iexact=entry.title, feed=self)
            except Article.DoesNotExist:
                article = Article(headline=entry.title, 
                    content=getattr(entry, 'summary', ''),
                    url=getattr(entry, 'link', self.url),
                    pub_date=getattr(entry, 'updated_parsed', datetime.datetime.now()),
                    feed=self
                )
                if isinstance(article.pub_date, time.struct_time):
                    article.pub_date = datetime.datetime(*[int(x) for x in article.pub_date[:6]])
                
            add_to_categories = []
            
            for category in self.categories.all():
                relationship_queryset = FeedCategoryRelationship.objects.filter(feed=self, category=category)
                article_passes = True
                
                for relationship in relationship_queryset.all():
                    if not article_passes:
                        continue
                    
                    whitelist = []
                    for white_list in relationship.white_list.all():
                        whitelist += white_list.keywords.split(',')
                    
                    if whitelist:
                        if not re.search(re.compile(r'(%s)' % '|'.join([s.strip() for s in whitelist if s.strip()]), re.IGNORECASE), article.headline):
                            article_passes = False
                            continue
                    
                    blacklist = []
                    for black_list in relationship.black_list.all():
                        blacklist += black_list.keywords.split(',')
                    
                    if blacklist:
                        if re.search(re.compile(r'(%s)' % '|'.join([s.strip() for s in whitelist if s.strip()]), re.IGNORECASE), article.headline):
                            article_passes = False
                            continue
                    
                    if DEFAULT_BLOCKED_HTML:
                        article.content = re.sub(ALLOWED_REGEX, '', article.content)
                        
                    if DEFAULT_ALLOWED_HTML:
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
    black_list = models.ManyToManyField(BlackListFilter, blank=True)

class Article(models.Model):
    headline = models.CharField(max_length=255)
    slug = models.SlugField()
    pub_date = models.DateField(default=datetime.datetime.now)
    url = models.URLField()
    content = models.TextField()
    
    feed = models.ForeignKey(Feed, related_name='articles')
    categories = models.ManyToManyField(Category, related_name='articles')
    
    class Meta:
        ordering = ('-pub_date', 'headline')
    
    def __unicode__(self):
        return u'%s' % self.headline
    
    def get_absolute_url(self):
        return self.url
