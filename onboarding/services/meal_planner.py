"""
Nouri — 7-Day Meal Plan Generator
Calls Claude API to generate a personalized weekly meal plan.
"""
import json
import logging

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

PERSONA_SYSTEM_PROMPTS = {
    'sarah': (
        "You are Dr. Sarah, a warm and empathetic Registered Dietitian with 15 years of clinical "
        "experience specializing in evidence-based nutrition therapy. You design meal plans that are "
        "practical, delicious, and therapeutic — every meal has a clinical purpose tied to the "
        "patient's goals and identified nutritional gaps. Your plans are realistic for busy people "
        "and never feel like punishment. You love simple ingredients, balanced plates, and meals "
        "that nourish both body and mind."
    ),
    'maya': (
        "You are Coach Maya, a high-performance sports nutritionist. You design meal plans optimized "
        "for energy, body composition, and recovery. Every meal is timed and structured to support "
        "training demands. You prioritize protein timing, complex carbohydrates around workouts, and "
        "anti-inflammatory foods for recovery. Your plans are bold, satisfying, and fuel-focused — "
        "food is performance medicine."
    ),
    'lena': (
        "You are Dr. Lena, a compassionate Registered Dietitian specializing in maternal and "
        "postpartum nutrition. You design gentle, nourishing meal plans that prioritize folate, "
        "iron, calcium, DHA, and other critical nutrients for mother and baby. Your meals are easy "
        "to prepare, safe during pregnancy, and deeply comforting. You always include foods rich in "
        "the nutrients most needed for each stage of pregnancy or postpartum recovery."
    ),
}


def _build_meal_plan_prompt(profile, analysis):
    """Build the user message for meal plan generation."""
    from datetime import date

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
    if profile.dietary_style:
        lines.append(f"- Dietary Style: {profile.dietary_style.replace('_', ' ').title()}")
    if profile.meal_frequency:
        lines.append(f"- Meals per Day: {profile.meal_frequency}")
    if profile.cooking_time:
        lines.append(f"- Max Cooking Time: {profile.cooking_time.replace('_', ' ')}")

    allergies = [a for a in (profile.food_allergies or []) if a not in ('none',)]
    if allergies:
        lines.append(f"- Food Allergies/Intolerances: {', '.join(allergies)}")
    if profile.food_allergies_other:
        lines.append(f"  Other allergy: {profile.food_allergies_other}")

    conditions = [c for c in (profile.medical_conditions or []) if c not in ('none',)]
    if conditions:
        lines.append(f"- Medical Conditions: {', '.join(conditions)}")

    restrictions = profile.diet_restrictions or []
    if restrictions:
        lines.append(f"- Dietary Goals: {', '.join(restrictions)}")

    if profile.food_dislikes:
        lines.append(f"- Foods to EXCLUDE (patient dislikes): {profile.food_dislikes}")
    if profile.medications:
        lines.append(f"- Medications: {profile.medications}")
    if profile.supplements:
        lines.append(f"- Current Supplements: {profile.supplements}")

    if analysis:
        lines.append("\n## DIETARY ANALYSIS RESULTS\n")
        if analysis.overall_score:
            lines.append(f"- Current Diet Quality Score: {analysis.overall_score}/100")

        nutrients = analysis.nutrients or {}
        cal = nutrients.get('calories', {})
        if cal:
            lines.append(f"- Current avg calories: {cal.get('value')} kcal/day")
        protein = nutrients.get('protein_g', {})
        if protein:
            lines.append(f"- Current avg protein: {protein.get('value')} g/day ({protein.get('dri_percent')}% of DRI)")

        deficiencies = analysis.deficiencies or []
        if deficiencies:
            lines.append(f"\n### Key Nutritional Gaps to Address:")
            for d in deficiencies:
                lines.append(f"- {d.get('nutrient')} ({d.get('severity')} deficiency): {d.get('impact', '')}")

        recs = analysis.recommendations or []
        if recs:
            lines.append(f"\n### Clinical Recommendations to Incorporate:")
            for r in recs[:5]:
                lines.append(f"- {r.get('title')}: {r.get('detail', '')[:120]}")

    lines.append("""
## TASK

Generate a personalized 7-day meal plan for this patient. Each day must include breakfast, lunch, dinner, and 1–2 snacks appropriate to their meal frequency preference.

CRITICAL RULES:
- NEVER include any food the patient is allergic to or dislikes
- Respect the dietary style (vegan, keto, halal, etc.) strictly
- Respect max cooking time per meal
- Address the identified nutritional deficiencies through food choices
- Vary meals across the week — no repeats of the same meal
- Include realistic portion sizes

Respond with ONLY a JSON object in this exact format:

```json
{
  "week_summary": "<2-3 sentence overview of the plan's clinical focus and approach>",
  "calorie_target": <integer, daily kcal target>,
  "macro_targets": {
    "protein_g": <integer>,
    "carbs_g": <integer>,
    "fat_g": <integer>,
    "fiber_g": <integer>
  },
  "days": [
    {
      "day_number": 1,
      "day_name": "Monday",
      "theme": "<short theme like 'High Protein Start' or 'Anti-Inflammatory Focus'>",
      "meals": {
        "breakfast": {
          "name": "<meal name>",
          "description": "<1-2 sentence appetizing description>",
          "calories": <integer>,
          "protein_g": <number>,
          "carbs_g": <number>,
          "fat_g": <number>,
          "prep_time_min": <integer>,
          "ingredients": ["<ingredient with quantity>"],
          "instructions": "<2-4 concise steps>",
          "tags": ["<e.g. High Protein, Quick, Meal Prep>"]
        },
        "morning_snack": <same structure or null>,
        "lunch": <same structure>,
        "afternoon_snack": <same structure or null>,
        "dinner": <same structure>
      },
      "day_totals": {
        "calories": <integer>,
        "protein_g": <number>,
        "carbs_g": <number>,
        "fat_g": <number>
      }
    }
  ]
}
```

Generate all 7 days (Monday through Sunday).
IMPORTANT: Be concise — keep instructions under 2 sentences, ingredients list max 6 items, description max 1 sentence. Return ONLY the JSON, no other text.
""")

    return "\n".join(lines)


def generate_meal_plan(profile, analysis=None):
    """
    Call Claude API and return parsed meal plan dict + raw response.
    Raises on API or parsing errors.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    persona_key = profile.persona if profile.persona in PERSONA_SYSTEM_PROMPTS else 'sarah'
    system_prompt = PERSONA_SYSTEM_PROMPTS[persona_key]
    user_message = _build_meal_plan_prompt(profile, analysis)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
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
