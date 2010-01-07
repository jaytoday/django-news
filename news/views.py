from django.conf import settings
from django.views.generic.list_detail import object_list
from django.shortcuts import get_object_or_404
from news.models import Category, Article

NEWS_ARTICLE_PAGINATION = getattr(settings, 'NEWS_ARTICLE_PAGINATION', 10)

def article_list(request, url_path='', template_name='news/article_list.html'):
    extra_context = { 'categories': Category.objects.all() }
    
    if url_path != '':
        category = get_object_or_404(Category, url_path=url_path)
        qs = category.articles.all()
        extra_context.update({ 'category': category })
    else:
        qs = Article.objects.all()
        
    if request.GET.get('q', None):
        qs = qs.filter(headline__icontains=request.GET['q'])
        extra_context.update({ 'search_query': request.GET['q'] })
        
    return object_list(
        request,
        queryset=qs,
        template_object_name='article',
        extra_context=extra_context,
        paginate_by=NEWS_ARTICLE_PAGINATION,
        page=int(request.GET.get('page', 0))
    )
