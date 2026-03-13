from django.urls import path
from . import views

app_name = 'onboarding'

urlpatterns = [
    path('',                          views.welcome,               name='welcome'),
    path('onboarding/',               views.persona,               name='onboarding'),
    path('onboarding/persona/',       views.persona,               name='persona'),
    path('onboarding/basic-profile/', views.basic_profile,         name='basic_profile'),
    path('onboarding/health-questionnaire/', views.health_questionnaire, name='health_questionnaire'),
    path('onboarding/diet-preferences/',     views.diet_preferences,    name='diet_preferences'),
    path('onboarding/food-recall/',          views.food_recall,         name='food_recall'),
    path('onboarding/analysis/',             views.analysis,            name='analysis'),
    path('onboarding/analyze/',              views.run_analysis,        name='run_analysis'),
    path('onboarding/analysis/results/',     views.analysis_results,    name='analysis_results'),
    path('onboarding/meal-plan/',            views.meal_plan,           name='meal_plan'),
    path('onboarding/meal-plan/generate/',   views.meal_plan_loading,   name='meal_plan_loading'),
    path('onboarding/meal-plan/create/',     views.generate_meal_plan,  name='generate_meal_plan'),
    path('onboarding/chat/',                 views.chat,                name='chat'),
    path('onboarding/chat/send/',            views.send_message,        name='send_message'),
    path('dashboard/',                       views.dashboard,           name='dashboard'),
    path('onboarding/weekly-report/',        views.weekly_report,       name='weekly_report'),
    path('onboarding/weekly-report/generate/', views.generate_weekly_report, name='generate_weekly_report'),
]
