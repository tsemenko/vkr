from django.shortcuts import redirect
from django.urls import reverse


class RequirePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._must_redirect(request):
            return redirect("change_initial_password")
        return self.get_response(request)

    def _must_redirect(self, request) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        allowed_paths = {
            reverse("change_initial_password"),
            reverse("logout"),
        }
        if request.path in allowed_paths or request.path.startswith("/admin/"):
            return False

        password_state = getattr(user, "password_state", None)
        return bool(password_state and password_state.must_change_password)
