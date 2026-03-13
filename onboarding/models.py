from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    PERSONA_CHOICES = [
        ('sarah', 'Dr. Sarah — Registered Dietitian'),
        ('maya', 'Coach Maya — Performance Specialist'),
        ('lena', 'Dr. Lena — Pregnancy & Postpartum RD'),
    ]
    SEX_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other / Prefer not to say'),
    ]
    GOAL_CHOICES = [
        ('lose_weight', 'Lose Weight'),
        ('gain_muscle', 'Gain Muscle'),
        ('eat_healthier', 'Eat Healthier'),
        ('manage_condition', 'Manage a Health Condition'),
        ('pregnancy', 'Pregnancy / Postpartum Support'),
        ('energy', 'More Energy'),
    ]
    ACTIVITY_CHOICES = [
        ('sedentary', 'Sedentary (little or no exercise)'),
        ('lightly_active', 'Lightly Active (1–3 days/week)'),
        ('moderately_active', 'Moderately Active (3–5 days/week)'),
        ('very_active', 'Very Active (6–7 days/week)'),
    ]

    # Step 1 — Persona
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    persona = models.CharField(max_length=20, choices=PERSONA_CHOICES, blank=True)

    # Step 2 — Basic profile
    date_of_birth = models.DateField(null=True, blank=True)
    biological_sex = models.CharField(max_length=10, choices=SEX_CHOICES, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    goal = models.CharField(max_length=30, choices=GOAL_CHOICES, blank=True)

    # Step 3 — Health questionnaire
    activity_level = models.CharField(max_length=20, choices=ACTIVITY_CHOICES, blank=True)
    medical_conditions = models.JSONField(default=list, blank=True)
    medical_conditions_other = models.CharField(max_length=255, blank=True)
    food_allergies = models.JSONField(default=list, blank=True)
    food_allergies_other = models.CharField(max_length=255, blank=True)
    medications = models.TextField(blank=True)
    supplements = models.TextField(blank=True)

    # Step 4 — Diet preferences
    dietary_style = models.CharField(max_length=30, blank=True)
    food_dislikes = models.TextField(blank=True)
    meal_frequency = models.CharField(max_length=20, blank=True)
    cooking_time = models.CharField(max_length=20, blank=True)
    diet_restrictions = models.JSONField(default=list, blank=True)
    diet_restrictions_other = models.CharField(max_length=255, blank=True)

    # Account tier
    is_premium  = models.BooleanField(default=False)
    demo_premium = models.BooleanField(default=False, help_text="Grant premium preview for this user")

    # Progress tracking
    onboarding_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} — {self.persona}"

    def get_persona_display_name(self):
        names = {'sarah': 'Dr. Sarah', 'maya': 'Coach Maya', 'lena': 'Dr. Lena'}
        return names.get(self.persona, 'Your Advisor')


class SiteConfig(models.Model):
    """Singleton — always use SiteConfig.get_solo()."""
    demo_mode = models.BooleanField(
        default=False,
        help_text="Enable demo/investor preview mode — all premium features visible for every user",
    )

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # prevent deletion

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Site Config — demo_mode={'ON' if self.demo_mode else 'OFF'}"


class FoodRecallDay(models.Model):
    DAY_CHOICES = [(1, 'Day 1'), (2, 'Day 2'), (3, 'Day 3')]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='food_recall_days')
    day_number = models.PositiveSmallIntegerField(choices=DAY_CHOICES)

    # Main meals — required for Day 1, optional for Days 2 & 3
    breakfast  = models.TextField(blank=True)
    lunch      = models.TextField(blank=True)
    dinner     = models.TextField(blank=True)

    # Snacks — always optional
    morning_snack   = models.TextField(blank=True)
    afternoon_snack = models.TextField(blank=True)
    evening_snack   = models.TextField(blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'day_number')
        ordering = ['day_number']

    def __str__(self):
        return f"{self.user.email} — Day {self.day_number}"

    def has_content(self):
        return any([self.breakfast, self.lunch, self.dinner,
                    self.morning_snack, self.afternoon_snack, self.evening_snack])


class DietaryAnalysis(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('running',   'Running'),
        ('complete',  'Complete'),
        ('error',     'Error'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dietary_analyses')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Structured output from Claude
    summary          = models.TextField(blank=True)
    persona_note     = models.TextField(blank=True)
    overall_score    = models.PositiveSmallIntegerField(null=True, blank=True)  # 0–100
    nutrients        = models.JSONField(default=dict, blank=True)
    deficiencies     = models.JSONField(default=list, blank=True)
    recommendations  = models.JSONField(default=list, blank=True)

    # Raw Claude response for debugging
    raw_response  = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.status} ({self.created_at:%Y-%m-%d})"


class MealPlan(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meal_plans')
    plan_json  = models.JSONField()
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — meal plan ({self.created_at:%Y-%m-%d})"


class MealSwap(models.Model):
    meal_plan     = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name='swaps')
    day           = models.IntegerField()
    meal_type     = models.CharField(max_length=20)
    original_meal = models.JSONField()
    swapped_meal  = models.JSONField()
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Swap day {self.day} {self.meal_type} — {self.meal_plan.user.email}"


class ChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]

    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    role        = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content     = models.TextField()
    is_food_log = models.BooleanField(default=False)
    meal_data   = models.JSONField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.email} [{self.role}] {self.created_at:%H:%M}"


class DailyMessageCount(models.Model):
    user  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_counts')
    date  = models.DateField()
    count = models.IntegerField(default=0)

    class Meta:
        unique_together = ['user', 'date']

    def __str__(self):
        return f"{self.user.email} — {self.date} ({self.count} messages)"


class WeeklyReport(models.Model):
    user            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='weekly_reports')
    week_start      = models.DateField()
    week_end        = models.DateField()

    # Core metrics
    adherence_score = models.PositiveSmallIntegerField(default=0)   # 0–100
    meals_followed  = models.PositiveSmallIntegerField(default=0)
    total_meals     = models.PositiveSmallIntegerField(default=0)

    # Structured content from Claude
    headline         = models.TextField(blank=True)
    wins             = models.JSONField(default=list)   # [{title, detail}]
    nutrient_summary = models.JSONField(default=list)   # [{name, avg_daily, target, unit, status}]
    focus_next_week  = models.JSONField(default=dict)   # {title, description, why}
    persona_closing  = models.TextField(blank=True)

    raw_response = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-week_start']
        unique_together = ['user', 'week_start']

    def __str__(self):
        return f"{self.user.email} — week of {self.week_start}"
