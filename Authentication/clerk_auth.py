import logging

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from .models import User


logger = logging.getLogger(__name__)


class ClerkAuthentication(authentication.BaseAuthentication):
    """Authenticate API requests using Clerk-issued bearer tokens."""

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token = parts[1]
        try:
            claims = self._verify_token(token)
            user = self._resolve_user(claims)
            return (user, claims)
        except exceptions.AuthenticationFailed:
            raise
        except Exception as exc:
            logger.exception("Unexpected Clerk auth error: %s", exc)
            raise exceptions.AuthenticationFailed("Authentication failed")

    def _verify_token(self, token):
        jwks_url = getattr(settings, "CLERK_JWKS_URL", "").strip()
        issuer = getattr(settings, "CLERK_ISSUER", "").strip()
        audience = getattr(settings, "CLERK_AUDIENCE", "").strip()

        if not jwks_url or not issuer:
            raise exceptions.AuthenticationFailed(
                "Server auth is not configured. Missing CLERK_JWKS_URL/CLERK_ISSUER"
            )

        try:
            signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
            decode_kwargs = {
                "key": signing_key.key,
                "algorithms": ["RS256"],
                "issuer": issuer,
                "options": {"verify_aud": bool(audience)},
            }
            if audience:
                decode_kwargs["audience"] = audience

            return jwt.decode(token, **decode_kwargs)
        except Exception as exc:
            logger.warning("Clerk token verification failed: %s", exc)
            raise exceptions.AuthenticationFailed("Invalid or expired token")

    def _resolve_user(self, claims):
        clerk_subject = claims.get("sub")
        if not clerk_subject:
            raise exceptions.AuthenticationFailed("Invalid token claims")

        email = (
            claims.get("email")
            or claims.get("email_address")
            or claims.get("primary_email_address")
        )
        if not email:
            email = f"{clerk_subject}@clerk.local"

        full_name = (
            claims.get("name")
            or claims.get("full_name")
            or " ".join(
                part
                for part in [claims.get("given_name"), claims.get("family_name")]
                if part
            ).strip()
            or email.split("@")[0]
        )

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": full_name,
            },
        )

        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])

        if full_name and user.full_name != full_name:
            user.full_name = full_name
            user.save(update_fields=["full_name"])

        return user
