"""
Nouri — Weekly Report Service
Generates a personalised weekly progress report using Claude API.
"""
import json
import logging
from datetime import date, timedelta

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)


def get_week_bounds():
    """Return (week_start, week_end) for the current ISO week (Mon–Sun)."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())       # Monday
    week_end   = week_start + timedelta(days=6)                # Sunday
    return week_start, week_end


def _build_report_prompt(profile, analysis, meal_plan, swaps, food_logs):
    from datetime import date as dt

    today = dt.today()
    age = None
    if profile.date_of_birth:
        age = today.year - profile.date_of_birth.year - (
            (today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day)
        )

    week_start, week_end = get_week_bounds()
    lines = [f"## WEEKLY REPORT — {week_start.strftime('%B %d')} to {week_end.strftime('%B %d, %Y')}\n"]
    lines.append("## PATIENT PROFILE")
    if age:              lines.append(f"- Age: {age}")
    if profile.biological_sex:  lines.append(f"- Sex: {profile.biological_sex}")
    if profile.goal:     lines.append(f"- Goal: {profile.goal.replace('_', ' ').title()}")
    if profile.activity_level:  lines.append(f"- Activity: {profile.activity_level.replace('_', ' ').title()}")
    if profile.dietary_style:   lines.append(f"- Diet style: {profile.dietary_style.replace('_', ' ').title()}")

    if analysis and analysis.status == 'complete':
        lines.append(f"\n## LATEST DIETARY ANALYSIS (score {analysis.overall_score}/100)")
        deficiencies = analysis.deficiencies or []
        if deficiencies:
            lines.append("Key deficiencies: " + ", ".join(d.get('nutrient', '') for d in deficiencies[:5]))
        nutrients = analysis.nutrients or {}
        for key in ['calories', 'protein_g', 'fiber_g', 'vitamin_d_mcg', 'calcium_mg', 'iron_mg']:
            nd = nutrients.get(key)
            if nd:
                lines.append(f"- {key}: {nd.get('value')} {nd.get('unit')} ({nd.get('dri_percent')}% DRI) — {nd.get('status')}")

    if meal_plan:
        plan_data = meal_plan.plan_json or {}
        lines.append(f"\n## ACTIVE MEAL PLAN")
        lines.append(f"- Calorie target: {plan_data.get('calorie_target')} kcal/day")
        mt = plan_data.get('macro_targets', {})
        if mt:
            lines.append(f"- Targets: {mt.get('protein_g')}g protein, {mt.get('carbs_g')}g carbs, {mt.get('fat_g')}g fat")

    if swaps:
        lines.append(f"\n## MEAL SWAPS THIS WEEK ({len(swaps)} meals logged differently via chat)")
        for s in swaps[:8]:
            sm = s.swapped_meal or {}
            lines.append(f"- Day {s.day} {s.meal_type}: replaced with '{sm.get('name', sm.get('description', 'unknown'))}'")

    if food_logs:
        lines.append(f"\n## FOOD LOGGED VIA CHAT THIS WEEK ({len(food_logs)} entries)")
        for fl in food_logs[:10]:
            md = fl.meal_data or {}
            lines.append(f"- {md.get('description', 'unknown')} (~{md.get('estimated_calories', '?')} kcal)")

    total_planned = 7 * 5   # 7 days × 5 meal slots
    meals_followed = max(0, total_planned - len(swaps))

    lines.append(f"""
## TASK

Generate a warm, personalised weekly progress report for this patient.
Total planned meals: {total_planned}. Meals followed as planned: {meals_followed}.
Meals logged differently: {len(swaps)}.

Respond ONLY with this JSON (no text outside it):

{{
  "headline": "<one energetic, personalised sentence celebrating or encouraging the week — max 12 words>",
  "adherence_score": <integer 0–100, based on meals followed vs total and overall engagement>,
  "meals_followed": {meals_followed},
  "total_meals": {total_planned},
  "wins": [
    {{"title": "<short win title>", "detail": "<1-2 sentences, warm and specific>"}},
    {{"title": "<short win title>", "detail": "<1-2 sentences>"}},
    {{"title": "<short win title>", "detail": "<1-2 sentences>"}}
  ],
  "nutrient_summary": [
    {{"name": "Calories", "avg_daily": <number>, "target": <number>, "unit": "kcal", "status": "on_track|low|high"}},
    {{"name": "Protein",  "avg_daily": <number>, "target": <number>, "unit": "g",    "status": "on_track|low|high"}},
    {{"name": "Fibre",    "avg_daily": <number>, "target": <number>, "unit": "g",    "status": "on_track|low|high"}},
    {{"name": "Vitamin D","avg_daily": <number>, "target": <number>, "unit": "mcg",  "status": "on_track|low|high"}},
    {{"name": "Calcium",  "avg_daily": <number>, "target": <number>, "unit": "mg",   "status": "on_track|low|high"}},
    {{"name": "Iron",     "avg_daily": <number>, "target": <number>, "unit": "mg",   "status": "on_track|low|high"}}
  ],
  "focus_next_week": {{
    "title": "<short, action-oriented title>",
    "description": "<2-3 specific, actionable sentences>",
    "why": "<1 sentence explaining clinical importance>"
  }},
  "persona_closing": "<2-3 sentence warm, encouraging closing message from the specialist persona>"
}}
""")
    return "\n".join(lines)


PERSONA_PROMPTS = {
    'sarah': (
        "You are Dr. Sarah, a warm Registered Dietitian generating a patient's weekly nutrition report. "
        "Be encouraging, evidence-based, and specific. Celebrate real wins. Be honest about gaps without being harsh."
    ),
    'maya': (
        "You are Coach Maya, a sports nutritionist generating a weekly performance nutrition report. "
        "Be direct, data-driven, and motivating. Focus on performance metrics and body composition progress."
    ),
    'lena': (
        "You are Dr. Lena, a maternal nutrition specialist generating a weekly report for your patient. "
        "Be gentle, reassuring, and supportive. Focus on nutrients critical for mother and baby."
    ),
}


def generate_weekly_report(profile, analysis, meal_plan, swaps, food_logs):
    """
    Call Claude API and return parsed report dict + raw response.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    persona_key   = profile.persona if profile.persona in PERSONA_PROMPTS else 'sarah'
    system_prompt = PERSONA_PROMPTS[persona_key]
    user_message  = _build_report_prompt(profile, analysis, meal_plan, swaps, food_logs)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    parsed = json.loads(raw)
    return parsed, response.content[0].text
