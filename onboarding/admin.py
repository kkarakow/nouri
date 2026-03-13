from django.contrib import admin
from .models import UserProfile, FoodRecallDay, SiteConfig


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'persona', 'goal', 'activity_level', 'is_premium', 'demo_premium', 'onboarding_complete', 'created_at')
    list_filter   = ('persona', 'goal', 'activity_level', 'is_premium', 'demo_premium', 'onboarding_complete')
    list_editable = ('is_premium', 'demo_premium')
    search_fields = ('user__email',)


@admin.register(FoodRecallDay)
class FoodRecallDayAdmin(admin.ModelAdmin):
    list_display  = ('user', 'day_number', 'has_content', 'updated_at')
    list_filter   = ('day_number',)
    search_fields = ('user__email',)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'demo_mode')

    def has_add_permission(self, request):
        # Only one row allowed
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
