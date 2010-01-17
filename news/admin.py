from django.contrib import admin
from news.models import Source, Category, Feed, Article, WhiteListFilter, FeedCategoryRelationship, CategoryRelationship

class FeedCategoryRelationshipInline(admin.TabularInline):
    model = FeedCategoryRelationship
    extra = 1

class CategoryRelationshipInline(admin.TabularInline):
    model = CategoryRelationship
    fk_name = 'category'
    extra = 1

class FeedAdmin(admin.ModelAdmin):
    inlines = (FeedCategoryRelationshipInline,)

class CategoryAdmin(admin.ModelAdmin):
    inlines = (FeedCategoryRelationshipInline, CategoryRelationshipInline)
    prepopulated_fields = { "slug": ("name",) }

class ArticleAdmin(admin.ModelAdmin):
    date_hierarchy = 'publish'
    list_display = ('publish', 'headline', 'feed')
    search_fields = ['headline', 'content']


admin.site.register(Source)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Article, ArticleAdmin)
admin.site.register(WhiteListFilter)
