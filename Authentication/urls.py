from django.urls import path
from .views import *
from .barcode_views import barcode_scan_api

app_name = "Authentication"

urlpatterns = [
    path("register/", register, name="register"),
    path("login/", login_view, name="login"),
    path("profile/", get_profile_view, name="get_profile_view"),
    path("profile/health/", update_profile_health, name="update_profile_health"),
    # path("extract_ingredients/", extract_ingredients_api, name="extract_ingredients_api"),
    # path("extract_nutrition/", extract_nutrition_api, name="extract_nutrition_api"),
    path("result_api/",result_api, name="result_api"),
    path("barcode_scan_api/", barcode_scan_api, name="barcode_scan_api"),
    path('user-history/', get_user_history, name='user-history'),
    path("manual-entry/", manual_entry_api, name="manual_entry_api"),
    path("update-onboarding/", update_onboarding, name="update_onboarding"),
]
