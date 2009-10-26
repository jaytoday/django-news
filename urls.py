from django.conf.urls.defaults import *

urlpatterns = patterns('djangonews.views',
    url(r'^(?P<url_path>[/\w-]*)',
        view='article_list',
        name='djangonews_article_index'
    )
)
