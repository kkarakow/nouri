import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.conf import settings
from .models import UserProfile, DietaryAnalysis, MealPlan, ChatMessage, WeeklyReport, SiteConfig

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────

def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def effective_premium(profile):
    """Returns True if the user has effective premium access (paid, demo flag, or global demo mode)."""
    demo_mode = getattr(settings, "DEMO_MODE", False)
    if not demo_mode:
        try:
            demo_mode = SiteConfig.get_solo().demo_mode
        except Exception:
            pass
    return profile.is_premium or profile.demo_premium or demo_mode


# ─── Welcome ─────────────────────────────────────────────────────────────────

def welcome(request):
    if request.user.is_authenticated:
        return redirect('onboarding:persona')
    pillars = ['47-Nutrient Analysis', 'AI Meal Plans', 'Smart Food Logging',
               'Weekly Progress Reports', 'Expert Dietitian-Designed']
    return render(request, 'onboarding/welcome.html', {'pillars': pillars})


# ─── Persona ─────────────────────────────────────────────────────────────────

def persona(request):
    selected = None
    error = None

    if request.user.is_authenticated:
        profile = get_or_create_profile(request.user)
        selected = profile.persona

    if request.method == 'POST':
        chosen = request.POST.get('persona')
        if chosen not in ('sarah', 'maya', 'lena'):
            error = 'Please choose an advisor to continue.'
        else:
            if request.user.is_authenticated:
                profile = get_or_create_profile(request.user)
                profile.persona = chosen
                profile.save()
                return redirect('onboarding:basic_profile')
            else:
                request.session['persona'] = chosen
                return redirect('onboarding:basic_profile')

    return render(request, 'onboarding/persona.html', {
        'selected': selected or request.session.get('persona', ''),
        'error': error,
    })


# ─── Basic Profile ────────────────────────────────────────────────────────────

def basic_profile(request):
    profile = None
    if request.user.is_authenticated:
        profile = get_or_create_profile(request.user)

    sex_choices = UserProfile.SEX_CHOICES
    goal_choices = UserProfile.GOAL_CHOICES
    error = None

    if request.method == 'POST':
        dob    = request.POST.get('date_of_birth', '').strip()
        sex    = request.POST.get('biological_sex', '').strip()
        weight = request.POST.get('weight_kg', '').strip()
        height = request.POST.get('height_cm', '').strip()
        goal   = request.POST.get('goal', '').strip()

        if not all([dob, sex, weight, height, goal]):
            error = 'Please complete all fields before continuing.'
        else:
            if request.user.is_authenticated:
                profile = get_or_create_profile(request.user)
                if not profile.persona and request.session.get('persona'):
                    profile.persona = request.session.pop('persona')
                profile.date_of_birth = dob
                profile.biological_sex = sex
                profile.weight_kg = float(weight)
                profile.height_cm = float(height)
                profile.goal = goal
                profile.save()
                return redirect('onboarding:health_questionnaire')
            else:
                request.session['basic_profile'] = {
                    'date_of_birth': dob, 'biological_sex': sex,
                    'weight_kg': weight, 'height_cm': height, 'goal': goal,
                }
                return redirect('/accounts/signup/')

    return render(request, 'onboarding/basic_profile.html', {
        'profile': profile,
        'sex_choices': sex_choices,
        'goal_choices': goal_choices,
        'error': error,
    })


# ─── Health Questionnaire ─────────────────────────────────────────────────────

MEDICAL_CONDITIONS = [
    ('diabetes',         'Diabetes (Type 1 or 2)', '🩸'),
    ('hypertension',     'High Blood Pressure',    '❤️'),
    ('high_cholesterol', 'High Cholesterol',        '🫀'),
    ('thyroid',          'Thyroid Issues',          '🦋'),
    ('ibs_ibd',          'IBS / IBD',              '🌿'),
    ('pcos',             'PCOS',                   '🌸'),
    ('none',             'None of the above',      '✓'),
    ('other',            'Other',                  '➕'),
]

FOOD_ALLERGIES = [
    ('gluten',    'Gluten / Wheat', '🌾'),
    ('dairy',     'Dairy',          '🥛'),
    ('eggs',      'Eggs',           '🥚'),
    ('nuts',      'Tree Nuts',      '🥜'),
    ('shellfish', 'Shellfish',      '🦐'),
    ('soy',       'Soy',           '🫘'),
    ('none',      'No allergies',   '✓'),
    ('other',     'Other',         '➕'),
]


@login_required
def health_questionnaire(request):
    profile = get_or_create_profile(request.user)
    error = None

    selected_conditions = profile.medical_conditions or []
    selected_allergies  = profile.food_allergies or []
    persona_name = profile.get_persona_display_name()

    if request.method == 'POST':
        activity    = request.POST.get('activity_level', '').strip()
        conditions  = request.POST.getlist('medical_conditions')
        allergies   = request.POST.getlist('food_allergies')
        med_other   = request.POST.get('medical_conditions_other', '').strip()
        all_other   = request.POST.get('food_allergies_other', '').strip()
        medications = request.POST.get('medications', '').strip()
        supplements = request.POST.get('supplements', '').strip()

        if not activity:
            error = 'Please select your activity level to continue.'
        else:
            profile.activity_level           = activity
            profile.medical_conditions       = conditions
            profile.medical_conditions_other = med_other
            profile.food_allergies           = allergies
            profile.food_allergies_other     = all_other
            profile.medications              = medications
            profile.supplements              = supplements
            profile.save()
            return redirect('onboarding:diet_preferences')

        selected_conditions = conditions
        selected_allergies  = allergies

    return render(request, 'onboarding/health_questionnaire.html', {
        'profile':             profile,
        'persona_name':        persona_name,
        'medical_conditions':  MEDICAL_CONDITIONS,
        'food_allergies':      FOOD_ALLERGIES,
        'selected_conditions': selected_conditions,
        'selected_allergies':  selected_allergies,
        'error':               error,
    })


# ─── Diet Preferences ─────────────────────────────────────────────────────────

DIETARY_STYLES = [
    ('no_restriction', 'No Restrictions',       '🍽️',  'I eat everything'),
    ('mediterranean',  'Mediterranean',          '🫒',  'Olive oil, fish, veggies, whole grains'),
    ('vegetarian',     'Vegetarian',             '🥦',  'No meat, fish is okay'),
    ('vegan',          'Vegan',                  '🌱',  'No animal products'),
    ('pescatarian',    'Pescatarian',            '🐟',  'Fish & seafood, no other meat'),
    ('keto',           'Keto / Low-Carb',        '🥑',  'High fat, very low carbohydrates'),
    ('paleo',          'Paleo',                  '🍖',  'Whole foods, no grains or legumes'),
    ('halal',          'Halal',                  '🌙',  'Halal-certified foods only'),
    ('kosher',         'Kosher',                 '✡️',  'Kosher dietary laws'),
]

MEAL_FREQUENCIES = [
    ('2',   '2 meals / day',   '2x'),
    ('3',   '3 meals / day',   '3x'),
    ('4',   '4 meals / day',   '4x'),
    ('5',   '5+ meals / day',  '5x'),
    ('if',  'Intermittent Fasting', 'IF'),
]

COOKING_TIMES = [
    ('under_15',  'Under 15 min',   '⚡'),
    ('15_30',     '15–30 min',      '🕐'),
    ('30_60',     '30–60 min',      '🍳'),
    ('over_60',   'I love cooking', '👨‍🍳'),
]

DIET_RESTRICTIONS = [
    ('low_sodium',   'Low Sodium',        '🧂'),
    ('low_sugar',    'Low Sugar',         '🍬'),
    ('low_fat',      'Low Fat',           '💧'),
    ('high_protein', 'High Protein',      '💪'),
    ('high_fiber',   'High Fibre',        '🌾'),
    ('low_fodmap',   'Low FODMAP',        '🥗'),
    ('diabetic',     'Diabetic-Friendly', '📊'),
    ('other',        'Other',             '➕'),
]


@login_required
def diet_preferences(request):
    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    error = None

    selected_restrictions = profile.diet_restrictions or []

    if request.method == 'POST':
        style       = request.POST.get('dietary_style', '').strip()
        dislikes    = request.POST.get('food_dislikes', '').strip()
        freq        = request.POST.get('meal_frequency', '').strip()
        cook_time   = request.POST.get('cooking_time', '').strip()
        restrictions = request.POST.getlist('diet_restrictions')
        rest_other  = request.POST.get('diet_restrictions_other', '').strip()

        if not style:
            error = 'Please select a dietary style to continue.'
        elif not freq:
            error = 'Please select how many meals per day you prefer.'
        elif not cook_time:
            error = 'Please select your preferred cooking time.'
        else:
            profile.dietary_style           = style
            profile.food_dislikes           = dislikes
            profile.meal_frequency          = freq
            profile.cooking_time            = cook_time
            profile.diet_restrictions       = restrictions
            profile.diet_restrictions_other = rest_other
            profile.save()
            return redirect('onboarding:food_recall')

        selected_restrictions = restrictions

    return render(request, 'onboarding/diet_preferences.html', {
        'profile':              profile,
        'persona_name':         persona_name,
        'dietary_styles':       DIETARY_STYLES,
        'meal_frequencies':     MEAL_FREQUENCIES,
        'cooking_times':        COOKING_TIMES,
        'diet_restrictions':    DIET_RESTRICTIONS,
        'selected_restrictions': selected_restrictions,
        'error':                error,
    })


# ─── Food Recall — Step 5 ────────────────────────────────────────────────────

@login_required
def food_recall(request):
    from .models import FoodRecallDay

    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()

    # Load existing entries (or empty dicts) for each day
    existing = {d.day_number: d for d in FoodRecallDay.objects.filter(user=request.user)}
    days_data = [existing.get(n) for n in (1, 2, 3)]  # index 0 = Day 1

    error = None

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        # Collect data for all 3 days
        saved_any = False
        error_day = None

        for n in (1, 2, 3):
            prefix = f'd{n}_'
            breakfast  = request.POST.get(f'{prefix}breakfast', '').strip()
            lunch      = request.POST.get(f'{prefix}lunch', '').strip()
            dinner     = request.POST.get(f'{prefix}dinner', '').strip()
            m_snack    = request.POST.get(f'{prefix}morning_snack', '').strip()
            a_snack    = request.POST.get(f'{prefix}afternoon_snack', '').strip()
            e_snack    = request.POST.get(f'{prefix}evening_snack', '').strip()
            notes      = request.POST.get(f'{prefix}notes', '').strip()

            has_any = any([breakfast, lunch, dinner, m_snack, a_snack, e_snack])

            if n == 1 and not has_any:
                error_day = 1
                break

            if has_any:
                FoodRecallDay.objects.update_or_create(
                    user=request.user,
                    day_number=n,
                    defaults=dict(
                        breakfast=breakfast, lunch=lunch, dinner=dinner,
                        morning_snack=m_snack, afternoon_snack=a_snack,
                        evening_snack=e_snack, notes=notes,
                    )
                )
                saved_any = True

        if error_day:
            error = 'Please log at least your meals for Day 1 to continue.'
            # Reload updated days_data for re-render
            existing = {d.day_number: d for d in FoodRecallDay.objects.filter(user=request.user)}
            days_data = [existing.get(n) for n in (1, 2, 3)]
        else:
            profile.onboarding_complete = True
            profile.save()
            return redirect('onboarding:analysis')

    labels = ['Day 1 — Today', 'Day 2 — Yesterday', 'Day 3 — Two Days Ago']
    day_rows = [
        (n, labels[n - 1], days_data[n - 1], n == 1)
        for n in (1, 2, 3)
    ]

    return render(request, 'onboarding/food_recall.html', {
        'profile':      profile,
        'persona_name': persona_name,
        'day_rows':     day_rows,
        'error':        error,
    })


# ─── Analysis — HTMX loading page ────────────────────────────────────────────

@login_required
def analysis(request):
    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    return render(request, 'onboarding/analysis.html', {'persona_name': persona_name})


# ─── Analysis — run (called by HTMX) ─────────────────────────────────────────

@login_required
def run_analysis(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    from .models import FoodRecallDay
    from .services import analyze_diet, NUTRIENT_CATEGORIES

    profile = get_or_create_profile(request.user)
    recall_days = list(FoodRecallDay.objects.filter(user=request.user).order_by('day_number'))

    # Create a new analysis record
    analysis_obj = DietaryAnalysis.objects.create(user=request.user, status='running')

    try:
        parsed, raw_text = analyze_diet(profile, recall_days)
        analysis_obj.status          = 'complete'
        analysis_obj.overall_score   = parsed.get('overall_score')
        analysis_obj.summary         = parsed.get('summary', '')
        analysis_obj.persona_note    = parsed.get('persona_note', '')
        analysis_obj.nutrients       = parsed.get('nutrients', {})
        analysis_obj.deficiencies    = parsed.get('deficiencies', [])
        analysis_obj.recommendations = parsed.get('recommendations', [])
        analysis_obj.raw_response    = raw_text
        analysis_obj.save()
    except Exception as exc:
        logger.exception("Diet analysis failed for user %s", request.user.email)
        analysis_obj.status        = 'error'
        analysis_obj.error_message = str(exc)
        analysis_obj.save()

    response = HttpResponse(status=200)
    response['HX-Redirect'] = f'/onboarding/analysis/results/?id={analysis_obj.pk}'
    return response


# ─── Analysis results page ────────────────────────────────────────────────────

@login_required
def analysis_results(request):
    from .services import NUTRIENT_CATEGORIES

    analysis_id = request.GET.get('id')
    if analysis_id:
        try:
            analysis_obj = DietaryAnalysis.objects.get(pk=analysis_id, user=request.user)
        except DietaryAnalysis.DoesNotExist:
            analysis_obj = DietaryAnalysis.objects.filter(user=request.user).first()
    else:
        analysis_obj = DietaryAnalysis.objects.filter(user=request.user).first()

    if not analysis_obj:
        return redirect('onboarding:analysis')

    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    is_premium = effective_premium(profile)

    # Build nutrient groups with gating
    nutrient_data = analysis_obj.nutrients or {}
    FREE_MACRO_KEYS = {
        'calories', 'protein_g', 'carbohydrates_g', 'fat_g', 'fiber_g',
        'vitamin_d_mcg', 'calcium_mg', 'iron_mg', 'vitamin_c_mg', 'omega3_mg',
    }

    nutrient_groups = []
    for category, keys in NUTRIENT_CATEGORIES.items():
        items = []
        for key in keys:
            nd = nutrient_data.get(key)
            if not nd:
                continue
            locked = not is_premium and key not in FREE_MACRO_KEYS
            items.append({
                'key': key,
                'label': key.replace('_', ' ').replace(' g', '').replace(' mg', '').replace(' mcg', '').replace(' ml', '').title(),
                'value': nd.get('value'),
                'unit': nd.get('unit', ''),
                'dri_percent': nd.get('dri_percent', 0),
                'status': nd.get('status', 'adequate'),
                'locked': locked,
            })
        if items:
            nutrient_groups.append({'category': category, 'items': items})

    # Gate recommendations
    recommendations = analysis_obj.recommendations or []
    if not is_premium:
        recommendations = recommendations[:3]

    deficiencies = analysis_obj.deficiencies or []

    return render(request, 'onboarding/analysis_results.html', {
        'analysis':         analysis_obj,
        'profile':          profile,
        'persona_name':     persona_name,
        'is_premium':       is_premium,
        'nutrient_groups':  nutrient_groups,
        'deficiencies':     deficiencies,
        'recommendations':  recommendations,
    })


# ─── Meal Plan — loading page ─────────────────────────────────────────────────

@login_required
def meal_plan_loading(request):
    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    return render(request, 'onboarding/meal_plan_loading.html', {'persona_name': persona_name})


# ─── Meal Plan — generate (called by HTMX) ───────────────────────────────────

@login_required
def generate_meal_plan(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    from .services import generate_meal_plan as _generate

    profile = get_or_create_profile(request.user)
    analysis = DietaryAnalysis.objects.filter(user=request.user, status='complete').first()

    # Deactivate old plans
    MealPlan.objects.filter(user=request.user).update(is_active=False)

    try:
        parsed, _ = _generate(profile, analysis)
        meal_plan = MealPlan.objects.create(
            user=request.user,
            plan_json=parsed,
            is_active=True,
        )
    except Exception as exc:
        logger.exception("Meal plan generation failed for user %s", request.user.email)
        response = HttpResponse(status=200)
        response['HX-Redirect'] = '/onboarding/meal-plan/?error=1'
        return response

    response = HttpResponse(status=200)
    response['HX-Redirect'] = f'/onboarding/meal-plan/?id={meal_plan.pk}'
    return response


# ─── Meal Plan — results page ─────────────────────────────────────────────────

@login_required
def meal_plan(request):
    plan_id = request.GET.get('id')
    error   = request.GET.get('error')

    if plan_id:
        try:
            plan_obj = MealPlan.objects.get(pk=plan_id, user=request.user)
        except MealPlan.DoesNotExist:
            plan_obj = MealPlan.objects.filter(user=request.user, is_active=True).first()
    else:
        plan_obj = MealPlan.objects.filter(user=request.user, is_active=True).first()

    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()

    if not plan_obj and not error:
        return redirect('onboarding:meal_plan_loading')

    days = []
    if plan_obj:
        plan_data = plan_obj.plan_json or {}
        days = plan_data.get('days', [])

    MEAL_ORDER = ['breakfast', 'morning_snack', 'lunch', 'afternoon_snack', 'dinner']
    MEAL_LABELS = {
        'breakfast':       ('🌅', 'Breakfast'),
        'morning_snack':   ('🍎', 'Morning Snack'),
        'lunch':           ('☀️',  'Lunch'),
        'afternoon_snack': ('🥜', 'Afternoon Snack'),
        'dinner':          ('🌙', 'Dinner'),
    }

    return render(request, 'onboarding/meal_plan.html', {
        'plan':         plan_obj,
        'days':         days,
        'profile':      profile,
        'persona_name': persona_name,
        'meal_order':   MEAL_ORDER,
        'meal_labels':  MEAL_LABELS,
        'error':        error,
    })


# ─── Chat ─────────────────────────────────────────────────────────────────────

@login_required
def chat(request):
    from .services.chat_service import FREE_DAILY_LIMIT
    from datetime import date

    profile = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    is_premium = effective_premium(profile)

    messages = ChatMessage.objects.filter(user=request.user).order_by('created_at')

    # Daily limit info for free users
    from .models import DailyMessageCount
    today = date.today()
    day_obj, _ = DailyMessageCount.objects.get_or_create(user=request.user, date=today)
    remaining = FREE_DAILY_LIMIT - day_obj.count if not is_premium else 999

    return render(request, 'onboarding/chat.html', {
        'profile':      profile,
        'persona_name': persona_name,
        'is_premium':   is_premium,
        'messages':     messages,
        'remaining':    remaining,
        'daily_limit':  FREE_DAILY_LIMIT,
    })


@login_required
def send_message(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    from .services import get_chat_response, check_and_increment_limit
    from .models import DailyMessageCount

    profile = get_or_create_profile(request.user)
    is_premium = effective_premium(profile)
    user_text = request.POST.get('message', '').strip()

    if not user_text:
        return HttpResponse('')

    # Check daily limit
    allowed, remaining = check_and_increment_limit(request.user, is_premium)
    if not allowed:
        return render(request, 'onboarding/_chat_limit.html', {
            'persona_name': profile.get_persona_display_name(),
        })

    # Save user message
    user_msg = ChatMessage.objects.create(
        user=request.user,
        role='user',
        content=user_text,
    )

    # Get AI response
    analysis  = DietaryAnalysis.objects.filter(user=request.user, status='complete').first()
    meal_plan = MealPlan.objects.filter(user=request.user, is_active=True).first()

    from .services.chat_service import update_meal_plan_from_log

    try:
        display_text, is_food_log, meal_data = get_chat_response(
            user=request.user,
            user_message=user_text,
            profile=profile,
            analysis=analysis,
            meal_plan=meal_plan,
        )
    except Exception as exc:
        logger.exception("Chat error for user %s", request.user.email)
        display_text = "I'm having a moment — please try again in a few seconds."
        is_food_log = False
        meal_data = None

    # Bug 2: update meal plan when food is logged
    meal_updated = False
    meal_slot = None
    if is_food_log and meal_data and meal_plan:
        meal_updated, meal_slot = update_meal_plan_from_log(request.user, meal_data)
        if meal_updated:
            display_text += " ✓ I've updated your meal plan for today."

    # Bug 1: save clean display_text (not raw JSON) as content
    ai_msg = ChatMessage.objects.create(
        user=request.user,
        role='assistant',
        content=display_text,
        is_food_log=is_food_log,
        meal_data=meal_data,
    )

    persona_name = profile.get_persona_display_name()

    return render(request, 'onboarding/_chat_messages.html', {
        'user_msg':     user_msg,
        'ai_msg':       ai_msg,
        'display_text': display_text,
        'is_food_log':  is_food_log,
        'meal_data':    meal_data,
        'persona_name': persona_name,
        'remaining':    remaining,
        'meal_updated': meal_updated,
        'meal_slot':    meal_slot,
    })


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    from datetime import date, timedelta

    profile      = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    analysis     = DietaryAnalysis.objects.filter(user=request.user, status='complete').first()
    meal_plan    = MealPlan.objects.filter(user=request.user, is_active=True).first()
    latest_report = WeeklyReport.objects.filter(user=request.user).first()

    # Banner: show if 7+ days since last report (or no report yet) and onboarding is done
    show_report_banner = False
    if profile.onboarding_complete:
        if not latest_report:
            show_report_banner = True
        elif (date.today() - latest_report.created_at.date()).days >= 7:
            show_report_banner = True

    return render(request, 'onboarding/dashboard.html', {
        'profile':             profile,
        'persona_name':        persona_name,
        'analysis':            analysis,
        'meal_plan':           meal_plan,
        'latest_report':       latest_report,
        'show_report_banner':  show_report_banner,
    })


# ─── Weekly Report ────────────────────────────────────────────────────────────

@login_required
def weekly_report(request):
    from .services import get_week_bounds

    profile      = get_or_create_profile(request.user)
    persona_name = profile.get_persona_display_name()
    is_premium   = effective_premium(profile)

    week_start, week_end = get_week_bounds()
    report = WeeklyReport.objects.filter(user=request.user, week_start=week_start).first()
    if not report:
        report = WeeklyReport.objects.filter(user=request.user).first()

    return render(request, 'onboarding/weekly_report.html', {
        'report':       report,
        'profile':      profile,
        'persona_name': persona_name,
        'is_premium':   is_premium,
        'week_start':   week_start,
        'week_end':     week_end,
    })


@login_required
def generate_weekly_report(request):
    from datetime import timedelta
    from .services import generate_weekly_report as _generate, get_week_bounds
    from .models import MealSwap

    profile   = get_or_create_profile(request.user)
    analysis  = DietaryAnalysis.objects.filter(user=request.user, status='complete').first()
    meal_plan = MealPlan.objects.filter(user=request.user, is_active=True).first()

    week_start, week_end = get_week_bounds()

    # Collect this week's data
    swaps = list(MealSwap.objects.filter(
        meal_plan__user=request.user,
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
    ).order_by('created_at'))

    food_logs = list(ChatMessage.objects.filter(
        user=request.user,
        role='assistant',
        is_food_log=True,
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
    ).order_by('created_at'))

    try:
        parsed, raw = _generate(profile, analysis, meal_plan, swaps, food_logs)

        report, _ = WeeklyReport.objects.update_or_create(
            user=request.user,
            week_start=week_start,
            defaults=dict(
                week_end        = week_end,
                adherence_score = parsed.get('adherence_score', 0),
                meals_followed  = parsed.get('meals_followed', 0),
                total_meals     = parsed.get('total_meals', 0),
                headline        = parsed.get('headline', ''),
                wins            = parsed.get('wins', []),
                nutrient_summary= parsed.get('nutrient_summary', []),
                focus_next_week = parsed.get('focus_next_week', {}),
                persona_closing = parsed.get('persona_closing', ''),
                raw_response    = raw,
            )
        )
    except Exception as exc:
        logger.exception("Weekly report generation failed for %s", request.user.email)
        return redirect('/onboarding/weekly-report/?error=1')

    return redirect(f'/onboarding/weekly-report/?id={report.pk}')
