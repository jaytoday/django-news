from django.conf.urls.defaults import *

urlpatterns = patterns('news.views',
    url(r'^(?P<url_path>[/\w-]*)',
        view='article_list',
        name='news_article_index'
    )
)
