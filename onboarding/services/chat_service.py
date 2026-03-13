"""
Nouri — AI Chat Service
Context-aware chat with the user's chosen specialist persona.
Handles conversational food logging automatically.
"""
import json
import logging
from datetime import date

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

FREE_DAILY_LIMIT = 20

# ─── Persona system prompts ───────────────────────────────────────────────────

_JSON_FORMAT_INSTRUCTION = """

RESPONSE FORMAT — CRITICAL:
You must ALWAYS respond with valid JSON only. Never include any text outside the JSON structure.
Every response must match this exact schema:

{
  "message": "<your conversational response to show the user>",
  "is_food_log": <true if the user mentioned eating something, false otherwise>,
  "meal_data": <null if not a food log, otherwise: {"description": "<what they ate>", "estimated_calories": <integer>, "protein_g": <number>, "carbs_g": <number>, "fat_g": <number>, "notes": "<one brief nutritional observation>"}>
}

Rules:
- "message" is always a plain text string — warm, concise, 1-4 sentences. No markdown, no bullet points unless asked.
- Set "is_food_log" to true when the user mentions eating or drinking anything (past or present: "I had", "I ate", "just had", "drank", "eating", etc.)
- When is_food_log is true, estimate macros from common nutrition databases. Be accurate.
- When is_food_log is false, meal_data must be null.
- Output ONLY the JSON object. No preamble, no explanation, no markdown fences."""

CHAT_PERSONA_PROMPTS = {
    'sarah': (
        "You are Dr. Sarah, a warm and empathetic Registered Dietitian with 15 years of clinical "
        "experience. You chat directly with your patient through their Nouri nutrition app. "
        "You are professional yet warm, encouraging, evidence-based, never judgmental. "
        "You give practical, personalised advice — never generic tips. "
        "You celebrate small wins and gently redirect when patients veer off track."
        + _JSON_FORMAT_INSTRUCTION
    ),
    'maya': (
        "You are Coach Maya, an energetic sports nutritionist chatting with your athlete through "
        "their Nouri nutrition app. You are motivating, direct, data-driven, high-energy. "
        "You focus on performance, body composition, fueling, and recovery. "
        "Every response drives action — no fluff, no vague advice."
        + _JSON_FORMAT_INSTRUCTION
    ),
    'lena': (
        "You are Dr. Lena, a gentle Registered Dietitian specialising in maternal and postpartum "
        "nutrition. You chat directly with your patient through their Nouri nutrition app. "
        "You are calm, reassuring, and deeply knowledgeable. You always consider mother and baby "
        "safety. You never cause alarm — you inform and support with warmth."
        + _JSON_FORMAT_INSTRUCTION
    ),
}


def _build_context(profile, analysis, meal_plan):
    """Build the system prompt context block about the user."""
    today = date.today()
    age = None
    if profile.date_of_birth:
        age = today.year - profile.date_of_birth.year - (
            (today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day)
        )

    lines = ["\n\n## YOUR PATIENT'S PROFILE\n"]
    if age:
        lines.append(f"- Age: {age}")
    if profile.biological_sex:
        lines.append(f"- Sex: {profile.biological_sex}")
    if profile.weight_kg and profile.height_cm:
        lines.append(f"- Weight: {profile.weight_kg}kg, Height: {profile.height_cm}cm")
    if profile.goal:
        lines.append(f"- Goal: {profile.goal.replace('_', ' ').title()}")
    if profile.activity_level:
        lines.append(f"- Activity: {profile.activity_level.replace('_', ' ').title()}")
    if profile.dietary_style:
        lines.append(f"- Diet style: {profile.dietary_style.replace('_', ' ').title()}")

    allergies = [a for a in (profile.food_allergies or []) if a != 'none']
    if allergies:
        lines.append(f"- Allergies: {', '.join(allergies)}")
    if profile.food_dislikes:
        lines.append(f"- Dislikes: {profile.food_dislikes}")

    conditions = [c for c in (profile.medical_conditions or []) if c != 'none']
    if conditions:
        lines.append(f"- Medical conditions: {', '.join(conditions)}")
    if profile.medications:
        lines.append(f"- Medications: {profile.medications}")

    if analysis and analysis.status == 'complete':
        lines.append(f"\n## DIETARY ANALYSIS (score: {analysis.overall_score}/100)")
        deficiencies = analysis.deficiencies or []
        if deficiencies:
            top = [d.get('nutrient') for d in deficiencies[:4]]
            lines.append(f"- Key deficiencies: {', '.join(top)}")
        nutrients = analysis.nutrients or {}
        cal = nutrients.get('calories', {})
        if cal:
            lines.append(f"- Current avg intake: {cal.get('value')} kcal/day")

    if meal_plan:
        plan_data = meal_plan.plan_json or {}
        lines.append(f"\n## ACTIVE MEAL PLAN")
        lines.append(f"- Calorie target: {plan_data.get('calorie_target')} kcal/day")
        mt = plan_data.get('macro_targets', {})
        if mt:
            lines.append(f"- Macro targets: {mt.get('protein_g')}g protein, {mt.get('carbs_g')}g carbs, {mt.get('fat_g')}g fat")

    return "\n".join(lines)


def get_chat_response(user, user_message, profile, analysis=None, meal_plan=None):
    """
    Send a message and get a structured JSON response from the persona.
    Returns (message_text, is_food_log, meal_data).
    Claude always returns {"message": ..., "is_food_log": ..., "meal_data": ...}.
    """
    from ..models import ChatMessage

    persona_key = profile.persona if profile.persona in CHAT_PERSONA_PROMPTS else 'sarah'
    system_prompt = CHAT_PERSONA_PROMPTS[persona_key] + _build_context(profile, analysis, meal_plan)

    # Conversation history — content is always clean text
    history = ChatMessage.objects.filter(user=user).order_by('-created_at')[:16]
    messages = [{"role": m.role, "content": m.content} for m in reversed(history)]
    messages.append({"role": "user", "content": user_message})

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    try:
        parsed = json.loads(raw)
        message_text = parsed.get("message", "").strip()
        is_food_log  = bool(parsed.get("is_food_log", False))
        meal_data    = parsed.get("meal_data") if is_food_log else None
    except (json.JSONDecodeError, AttributeError):
        # Fallback: treat entire response as plain message
        logger.warning("Claude returned non-JSON chat response: %s", raw[:200])
        message_text = raw
        is_food_log  = False
        meal_data    = None

    return message_text, is_food_log, meal_data


def update_meal_plan_from_log(user, meal_data):
    """
    Replace the closest meal slot in today's active meal plan with the logged food.
    Returns (success, meal_slot_name).
    """
    from datetime import datetime
    from ..models import MealPlan, MealSwap

    plan = MealPlan.objects.filter(user=user, is_active=True).first()
    if not plan:
        return False, None

    # Determine today's day number (1=Monday … 7=Sunday)
    today_day_number = datetime.today().weekday() + 1  # weekday() 0=Mon → 1

    # Pick meal slot by hour
    hour = datetime.now().hour
    if 5 <= hour < 10:
        meal_slot = 'breakfast'
    elif 10 <= hour < 12:
        meal_slot = 'morning_snack'
    elif 12 <= hour < 15:
        meal_slot = 'lunch'
    elif 15 <= hour < 18:
        meal_slot = 'afternoon_snack'
    else:
        meal_slot = 'dinner'

    plan_data = plan.plan_json or {}
    days = plan_data.get('days', [])

    # Find today's day entry
    today_entry = None
    day_index = None
    for i, day in enumerate(days):
        if day.get('day_number') == today_day_number:
            today_entry = day
            day_index = i
            break

    if today_entry is None or day_index is None:
        return False, None

    meals = today_entry.get('meals', {})
    original_meal = meals.get(meal_slot)

    # Build replacement meal from logged data
    swapped_meal = {
        'name': meal_data.get('description', 'Logged meal'),
        'description': meal_data.get('description', ''),
        'calories': meal_data.get('estimated_calories'),
        'protein_g': meal_data.get('protein_g'),
        'carbs_g': meal_data.get('carbs_g'),
        'fat_g': meal_data.get('fat_g'),
        'prep_time_min': 0,
        'ingredients': [],
        'instructions': 'Logged via chat.',
        'tags': ['Chat Logged'],
    }

    # Update plan JSON in-place
    plan_data['days'][day_index]['meals'][meal_slot] = swapped_meal

    # Recompute day totals
    new_totals = {'calories': 0, 'protein_g': 0.0, 'carbs_g': 0.0, 'fat_g': 0.0}
    for m in plan_data['days'][day_index]['meals'].values():
        if m:
            new_totals['calories']  += m.get('calories') or 0
            new_totals['protein_g'] += float(m.get('protein_g') or 0)
            new_totals['carbs_g']   += float(m.get('carbs_g') or 0)
            new_totals['fat_g']     += float(m.get('fat_g') or 0)
    plan_data['days'][day_index]['day_totals'] = new_totals

    plan.plan_json = plan_data
    plan.save(update_fields=['plan_json'])

    # Record the swap
    if original_meal:
        MealSwap.objects.create(
            meal_plan=plan,
            day=today_day_number,
            meal_type=meal_slot,
            original_meal=original_meal,
            swapped_meal=swapped_meal,
        )

    return True, meal_slot


def check_and_increment_limit(user, is_premium):
    """Returns (allowed, remaining). Increments count if allowed."""
    from ..models import DailyMessageCount

    if is_premium:
        return True, 999

    today = date.today()
    obj, _ = DailyMessageCount.objects.get_or_create(user=user, date=today)
    if obj.count >= FREE_DAILY_LIMIT:
        return False, 0

    obj.count += 1
    obj.save(update_fields=['count'])
    return True, FREE_DAILY_LIMIT - obj.count
