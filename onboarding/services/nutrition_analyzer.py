"""
Nouri — Dietary Analysis Service
Calls Claude API to generate a clinical nutrition analysis.
"""
import json
import logging
from datetime import date

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Persona system prompts ───────────────────────────────────────────────────

PERSONA_PROMPTS = {
    'sarah': (
        "You are Dr. Sarah, a warm and empathetic Registered Dietitian with 15 years of clinical "
        "experience. You specialize in evidence-based nutrition therapy for weight management, "
        "metabolic health, and chronic disease prevention. Your tone is professional but caring — "
        "you speak clearly, avoid jargon, and always focus on what's realistic and sustainable for "
        "each patient. You are thorough in your analysis and precise with numbers."
    ),
    'maya': (
        "You are Coach Maya, an energetic sports nutritionist and performance dietitian. You work "
        "with athletes and active individuals to optimize fueling, recovery, and body composition. "
        "Your tone is motivating, direct, and practical. You focus on performance metrics and "
        "actionable strategies. You love data and get excited about helping people unlock their "
        "physical potential through nutrition."
    ),
    'lena': (
        "You are Dr. Lena, a compassionate Registered Dietitian specializing in maternal nutrition, "
        "pregnancy, and postpartum recovery. You have deep expertise in prenatal micronutrient needs, "
        "gestational conditions, and supporting new mothers through breastfeeding and recovery. Your "
        "tone is gentle, supportive, and deeply reassuring. You always prioritize both mother and "
        "baby safety in every recommendation."
    ),
}

DEFAULT_PERSONA_PROMPT = PERSONA_PROMPTS['sarah']

# ─── Nutrient categories ──────────────────────────────────────────────────────

NUTRIENT_CATEGORIES = {
    'Macronutrients': [
        'calories', 'protein_g', 'carbohydrates_g', 'fat_g',
        'saturated_fat_g', 'fiber_g', 'sugar_g', 'water_ml',
    ],
    'Fat-Soluble Vitamins': ['vitamin_a_mcg', 'vitamin_d_mcg', 'vitamin_e_mg', 'vitamin_k_mcg'],
    'B Vitamins': [
        'thiamine_mg', 'riboflavin_mg', 'niacin_mg', 'b6_mg',
        'folate_mcg', 'b12_mcg', 'biotin_mcg', 'pantothenic_acid_mg',
    ],
    'Vitamin C': ['vitamin_c_mg'],
    'Major Minerals': ['calcium_mg', 'phosphorus_mg', 'magnesium_mg', 'sodium_mg', 'potassium_mg', 'chloride_mg'],
    'Trace Minerals': ['iron_mg', 'zinc_mg', 'copper_mg', 'manganese_mg', 'selenium_mcg', 'iodine_mcg', 'chromium_mcg', 'molybdenum_mcg'],
    'Essential Fatty Acids': ['omega3_mg', 'omega6_mg', 'dha_mg', 'epa_mg'],
    'Amino Acids (key)': ['leucine_g', 'lysine_g', 'tryptophan_g'],
    'Other': ['cholesterol_mg', 'caffeine_mg', 'alcohol_g'],
}


def _build_user_message(profile, recall_days):
    """Build the full patient profile + food recall message."""
    today = date.today()
    age = None
    if profile.date_of_birth:
        age = today.year - profile.date_of_birth.year - (
            (today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day)
        )

    lines = ["## PATIENT PROFILE\n"]
    if age:
        lines.append(f"- Age: {age} years")
    if profile.biological_sex:
        lines.append(f"- Biological Sex: {profile.biological_sex}")
    if profile.weight_kg:
        lines.append(f"- Weight: {profile.weight_kg} kg")
    if profile.height_cm:
        lines.append(f"- Height: {profile.height_cm} cm")
    if profile.goal:
        lines.append(f"- Primary Goal: {profile.goal.replace('_', ' ').title()}")
    if profile.activity_level:
        lines.append(f"- Activity Level: {profile.activity_level.replace('_', ' ').title()}")
    if profile.medical_conditions:
        conditions = [c for c in profile.medical_conditions if c not in ('none',)]
        if conditions:
            lines.append(f"- Medical Conditions: {', '.join(conditions)}")
        if profile.medical_conditions_other:
            lines.append(f"  Other: {profile.medical_conditions_other}")
    if profile.food_allergies:
        allergies = [a for a in profile.food_allergies if a not in ('none',)]
        if allergies:
            lines.append(f"- Food Allergies/Intolerances: {', '.join(allergies)}")
        if profile.food_allergies_other:
            lines.append(f"  Other: {profile.food_allergies_other}")
    if profile.medications:
        lines.append(f"- Medications: {profile.medications}")
    if profile.supplements:
        lines.append(f"- Supplements: {profile.supplements}")
    if profile.dietary_style:
        lines.append(f"- Dietary Style: {profile.dietary_style.replace('_', ' ').title()}")
    if profile.food_dislikes:
        lines.append(f"- Food Dislikes: {profile.food_dislikes}")
    if profile.meal_frequency:
        lines.append(f"- Meal Frequency: {profile.meal_frequency} meals/day")
    if profile.cooking_time:
        lines.append(f"- Cooking Time Available: {profile.cooking_time.replace('_', ' ')}")
    if profile.diet_restrictions:
        lines.append(f"- Additional Dietary Goals: {', '.join(profile.diet_restrictions)}")

    lines.append("\n## FOOD RECALL (last 1–3 days)\n")
    day_labels = {1: "Today", 2: "Yesterday", 3: "Two days ago"}
    for day in recall_days:
        lines.append(f"### Day {day.day_number} ({day_labels.get(day.day_number, f'Day {day.day_number}')})")
        if day.breakfast:
            lines.append(f"- Breakfast: {day.breakfast}")
        if day.lunch:
            lines.append(f"- Lunch: {day.lunch}")
        if day.dinner:
            lines.append(f"- Dinner: {day.dinner}")
        if day.morning_snack:
            lines.append(f"- Morning Snack: {day.morning_snack}")
        if day.afternoon_snack:
            lines.append(f"- Afternoon Snack: {day.afternoon_snack}")
        if day.evening_snack:
            lines.append(f"- Evening Snack: {day.evening_snack}")
        if day.notes:
            lines.append(f"- Notes: {day.notes}")
        lines.append("")

    lines.append("""
## TASK

Analyze this patient's diet and respond with a JSON object containing exactly these fields:

```json
{
  "overall_score": <integer 0-100, overall diet quality score>,
  "summary": "<2-3 sentence plain-language summary of the diet quality and main patterns>",
  "persona_note": "<1-2 sentence warm, persona-appropriate clinical observation or encouragement>",
  "nutrients": {
    "calories": {"value": <number>, "unit": "kcal", "dri_percent": <integer, % of DRI/RDA>, "status": "<optimal|adequate|low|high|critical>"},
    "protein_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "carbohydrates_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "fat_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "saturated_fat_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "fiber_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "sugar_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "water_ml": {"value": <number>, "unit": "ml", "dri_percent": <integer>, "status": "<status>"},
    "vitamin_a_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "vitamin_d_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "vitamin_e_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "vitamin_k_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "vitamin_c_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "thiamine_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "riboflavin_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "niacin_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "b6_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "folate_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "b12_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "biotin_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "pantothenic_acid_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "calcium_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "phosphorus_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "magnesium_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "sodium_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "potassium_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "chloride_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "iron_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "zinc_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "copper_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "manganese_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "selenium_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "iodine_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "chromium_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "molybdenum_mcg": {"value": <number>, "unit": "mcg", "dri_percent": <integer>, "status": "<status>"},
    "omega3_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "omega6_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "dha_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "epa_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "leucine_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "lysine_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "tryptophan_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"},
    "cholesterol_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "caffeine_mg": {"value": <number>, "unit": "mg", "dri_percent": <integer>, "status": "<status>"},
    "alcohol_g": {"value": <number>, "unit": "g", "dri_percent": <integer>, "status": "<status>"}
  },
  "deficiencies": [
    {
      "nutrient": "<display name>",
      "severity": "<mild|moderate|severe>",
      "impact": "<1 sentence clinical impact>",
      "food_sources": ["<food 1>", "<food 2>", "<food 3>"]
    }
  ],
  "recommendations": [
    {
      "title": "<short action title>",
      "detail": "<2-3 sentence specific, actionable recommendation>",
      "priority": "<high|medium|low>"
    }
  ]
}
```

Use average values across the days provided. Base DRI percentages on established DRI/RDA values for this patient's age, sex, and goal. List 3–7 deficiencies and 5–8 recommendations. Return ONLY the JSON object, no other text.
""")

    return "\n".join(lines)


def analyze_diet(profile, recall_days):
    """
    Call Claude API and return parsed analysis dict.
    Raises on API or parsing errors.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    persona_key = profile.persona if profile.persona in PERSONA_PROMPTS else 'sarah'
    system_prompt = PERSONA_PROMPTS[persona_key]
    user_message = _build_user_message(profile, recall_days)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3].strip()
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()

    parsed = json.loads(raw_text)
    return parsed, response.content[0].text
