import logging
import re

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from .models import User


logger = logging.getLogger(__name__)

PLACEHOLDER_EMAIL_DOMAIN = "@clerk.local"
PLACEHOLDER_NAME_PATTERN = re.compile(r"^user_[A-Za-z0-9]+$")


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
        email = email.strip().lower() if isinstance(email, str) and email.strip() else None
        real_email = None if self._is_placeholder_email(email) else email

        full_name = (
            claims.get("name")
            or claims.get("full_name")
            or " ".join(
                part
                for part in [claims.get("given_name"), claims.get("family_name")]
                if part
            ).strip()
            or (real_email or f"{clerk_subject}{PLACEHOLDER_EMAIL_DOMAIN}").split("@")[0]
        )
        full_name = full_name.strip() if isinstance(full_name, str) and full_name.strip() else None
        real_full_name = None if self._is_placeholder_name(full_name, clerk_subject) else full_name

        user = User.objects.filter(clerk_id=clerk_subject).first()

        if not user and real_email:
            user = User.objects.filter(email__iexact=real_email).first()
            if user and user.clerk_id and user.clerk_id != clerk_subject:
                logger.warning(
                    "Clerk email %s is already linked to a different Clerk subject",
                    real_email,
                )
                raise exceptions.AuthenticationFailed("Account conflict detected")

        created = False
        if not user:
            user, created = User.objects.get_or_create(
                email=real_email or f"{clerk_subject}{PLACEHOLDER_EMAIL_DOMAIN}",
                defaults={
                    "clerk_id": clerk_subject,
                    "full_name": real_full_name or clerk_subject,
                },
            )
        else:
            user = self._attach_clerk_id(user, clerk_subject)

        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])

        user = self._sync_identity_fields(
            user=user,
            clerk_subject=clerk_subject,
            real_email=real_email,
            real_full_name=real_full_name,
        )

        return user

    def _attach_clerk_id(self, user, clerk_subject):
        if user.clerk_id and user.clerk_id != clerk_subject:
            logger.warning(
                "User %s is already linked to a different Clerk subject",
                user.pk,
            )
            raise exceptions.AuthenticationFailed("Account conflict detected")

        if user.clerk_id != clerk_subject:
            user.clerk_id = clerk_subject
            user.save(update_fields=["clerk_id"])

        return user

    def _sync_identity_fields(self, user, clerk_subject, real_email, real_full_name):
        updates = []

        if not user.clerk_id:
            user.clerk_id = clerk_subject
            updates.append("clerk_id")

        if real_email and user.email != real_email:
            email_in_use = User.objects.filter(email__iexact=real_email).exclude(pk=user.pk).exists()
            if email_in_use:
                logger.warning(
                    "Skipping email sync for Clerk subject %s because %s is already used",
                    clerk_subject,
                    real_email,
                )
            elif self._is_placeholder_email(user.email):
                user.email = real_email
                updates.append("email")

        if real_full_name and user.full_name != real_full_name:
            if not user.full_name or self._is_placeholder_name(user.full_name, clerk_subject):
                user.full_name = real_full_name
                updates.append("full_name")

        if updates:
            user.save(update_fields=updates)

        return user

    def _is_placeholder_email(self, email):
        return not email or email.endswith(PLACEHOLDER_EMAIL_DOMAIN)

    def _is_placeholder_name(self, full_name, clerk_subject):
        if not full_name:
            return True

        normalized_name = full_name.strip()
        return normalized_name == clerk_subject or bool(
            PLACEHOLDER_NAME_PATTERN.fullmatch(normalized_name)
        )
