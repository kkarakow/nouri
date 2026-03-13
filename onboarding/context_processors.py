from django.conf import settings


def premium_status(request):
    """
    Injects `is_premium` and `is_demo_preview` into every template context.

    is_premium      — True when the user has effective premium access
                      (paid tier OR demo_premium flag OR global DEMO_MODE / SiteConfig toggle)
    is_demo_preview — True when premium access is demo-only (not a real paid subscriber),
                      used to show the "Premium Preview" banner instead of upgrade overlays.
    """
    if not request.user.is_authenticated:
        return {"is_premium": False, "is_demo_preview": False}

    try:
        profile = request.user.profile
    except Exception:
        return {"is_premium": False, "is_demo_preview": False}

    # Check global demo mode from settings first, then DB toggle
    demo_mode = getattr(settings, "DEMO_MODE", False)
    if not demo_mode:
        try:
            from .models import SiteConfig
            demo_mode = SiteConfig.get_solo().demo_mode
        except Exception:
            pass

    effective_premium = profile.is_premium or profile.demo_premium or demo_mode
    is_demo_preview = effective_premium and not profile.is_premium

    return {
        "is_premium": effective_premium,
        "is_demo_preview": is_demo_preview,
    }
