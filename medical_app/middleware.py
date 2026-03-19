from .models import LoginActivity, UserProfile


def _get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "").strip()


def _build_location_label(ip_address):
    if not ip_address:
        return "Unknown location"

    if ip_address in {"127.0.0.1", "::1"}:
        return "Local development machine"

    if ip_address.startswith(("10.", "172.", "192.168.")):
        return "Private network"

    return f"IP: {ip_address}"


def _build_device_name(user_agent):
    agent = (user_agent or "").lower()
    if "iphone" in agent:
        return "iPhone"
    if "ipad" in agent:
        return "iPad"
    if "android" in agent:
        return "Android device"
    if "windows" in agent:
        return "Windows desktop"
    if "mac os x" in agent or "macintosh" in agent:
        return "Mac desktop"
    if "linux" in agent:
        return "Linux machine"
    return "Unknown device"


def _build_browser_name(user_agent):
    agent = (user_agent or "").lower()
    if "edg/" in agent:
        return "Microsoft Edge"
    if "chrome/" in agent and "edg/" not in agent:
        return "Google Chrome"
    if "firefox/" in agent:
        return "Mozilla Firefox"
    if "safari/" in agent and "chrome/" not in agent:
        return "Safari"
    return "Browser"


class CurrentLoginActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if not request.session.session_key:
                request.session.save()

            session_key = request.session.session_key
            ip_address = _get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            location_label = _build_location_label(ip_address)

            LoginActivity.objects.update_or_create(
                user=request.user,
                session_key=session_key,
                defaults={
                    "ip_address": ip_address,
                    "location_label": location_label,
                    "device_name": _build_device_name(user_agent),
                    "browser_name": _build_browser_name(user_agent),
                    "user_agent": user_agent[:1000],
                    "is_active": True,
                },
            )

            existing_profile = UserProfile.objects.filter(user=request.user).first()
            UserProfile.objects.update_or_create(
                user=request.user,
                defaults={
                    "mobile_number": existing_profile.mobile_number if existing_profile else "",
                    "last_known_location": location_label,
                },
            )

        return self.get_response(request)
