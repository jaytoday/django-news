from django.contrib import admin
from djangonews.models import Source, Category, Feed, Article, WhiteListFilter, BlackListFilter, FeedCategoryRelationship

class FeedCategoryRelationshipInline(admin.TabularInline):
    model = FeedCategoryRelationship
    extra = 1

class FeedAdmin(admin.ModelAdmin):
    inlines = (FeedCategoryRelationshipInline,)

class CategoryAdmin(admin.ModelAdmin):
    inlines = (FeedCategoryRelationshipInline,)
    prepopulated_fields = { "slug": ("name",) }

class ArticleAdmin(admin.ModelAdmin):
    date_hierarchy = 'pub_date'
    list_display = ('pub_date', 'headline', 'feed')
    search_fields = ['headline', 'content']


admin.site.register(Source)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Article, ArticleAdmin)
admin.site.register(WhiteListFilter)
admin.site.register(BlackListFilter)
