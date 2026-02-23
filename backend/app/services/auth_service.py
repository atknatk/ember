"""Authentication service — Cognito signup/login/refresh, DB profile bootstrap.

All boto3 Cognito calls are wrapped with ``asyncio.to_thread`` to avoid
blocking the FastAPI async event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.character import Character
from app.models.conversation import Conversation
from app.models.profile import Profile
from app.schemas.auth import AuthResponse, RefreshResponse, UserResponse

logger = logging.getLogger("ember")

DEFAULT_COMPANION_PROMPT = (
    "You are {user_name}'s personal AI companion. "
    "You are a holistic life friend -- covering fitness, nutrition, work, stress, "
    "and relationships. "
    "You are warm, honest, and genuine but never overly positive. "
    "You remember everything about the user and get to know them better over time. "
    "Use what you know naturally -- never say 'I remember that...' -- just know it. "
    "Keep messages concise. Ask questions when needed, don't monologue."
)


class AuthService:
    """Handles registration, login, and token refresh via AWS Cognito."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._cognito_client: object | None = None

    @property
    def cognito(self) -> object:
        """Lazily initialise the boto3 Cognito Identity Provider client."""
        if self._cognito_client is None:
            self._cognito_client = boto3.client(
                "cognito-idp",
                region_name=settings.aws_region,
            )
        return self._cognito_client

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def register(
        self,
        email: str,
        password: str,
        name: str,
    ) -> AuthResponse:
        """Register a new user: Cognito signup + DB profile + default character.

        Steps:
            1. Cognito sign_up
            2. Cognito admin_confirm_sign_up (auto-confirm for MVP)
            3. Cognito initiate_auth to obtain tokens
            4. Decode IdToken for ``sub``
            5. Create Profile + Character + Conversation in a single DB transaction

        If Cognito signup returns UsernameExistsException, we attempt to
        authenticate the user. If auth succeeds and no profile row exists,
        we create the missing DB rows (idempotent recovery).
        """
        try:
            await asyncio.to_thread(
                self._cognito_sign_up,
                email,
                password,
                name,
            )
            await asyncio.to_thread(self._cognito_admin_confirm, email)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "UsernameExistsException":
                return await self._handle_existing_cognito_user(
                    email, password, name,
                )
            self._raise_cognito_error(code)

        return await self._authenticate_and_create_profile(email, password, name)

    async def login(self, email: str, password: str) -> AuthResponse:
        """Authenticate an existing user against Cognito and return tokens + profile."""
        auth_result = await self._cognito_initiate_auth(email, password)

        id_token: str = auth_result["AuthenticationResult"]["IdToken"]
        refresh_token: str = auth_result["AuthenticationResult"]["RefreshToken"]
        sub = self._extract_sub(id_token)

        profile = await self._get_profile(sub)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return AuthResponse(
            token=id_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(profile),
        )

    async def refresh(self, refresh_token: str) -> RefreshResponse:
        """Exchange a Cognito refresh token for a new ID token."""
        try:
            result = await asyncio.to_thread(
                self._cognito_refresh,
                refresh_token,
            )
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("NotAuthorizedException", "UserNotFoundException"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from exc

        id_token: str = result["AuthenticationResult"]["IdToken"]
        return RefreshResponse(token=id_token)

    # ------------------------------------------------------------------
    # Private — Cognito wrappers (synchronous, called via to_thread)
    # ------------------------------------------------------------------

    def _cognito_sign_up(
        self,
        email: str,
        password: str,
        name: str,
    ) -> dict[str, object]:
        return self.cognito.sign_up(  # type: ignore[union-attr]
            ClientId=settings.cognito_app_client_id,
            Username=email,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": name},
            ],
        )

    def _cognito_admin_confirm(self, email: str) -> dict[str, object]:
        return self.cognito.admin_confirm_sign_up(  # type: ignore[union-attr]
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
        )

    def _cognito_initiate_auth_sync(
        self,
        email: str,
        password: str,
    ) -> dict[str, object]:
        return self.cognito.initiate_auth(  # type: ignore[union-attr]
            ClientId=settings.cognito_app_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": email,
                "PASSWORD": password,
            },
        )

    def _cognito_refresh(self, refresh_token: str) -> dict[str, object]:
        return self.cognito.initiate_auth(  # type: ignore[union-attr]
            ClientId=settings.cognito_app_client_id,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={
                "REFRESH_TOKEN": refresh_token,
            },
        )

    # ------------------------------------------------------------------
    # Private — async Cognito helpers
    # ------------------------------------------------------------------

    async def _cognito_initiate_auth(
        self,
        email: str,
        password: str,
    ) -> dict[str, object]:
        """Call Cognito initiate_auth with USER_PASSWORD_AUTH, mapping errors."""
        try:
            result = await asyncio.to_thread(
                self._cognito_initiate_auth_sync,
                email,
                password,
            )
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("NotAuthorizedException", "UserNotFoundException"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                ) from exc
            if code == "UserNotConfirmedException":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User is not confirmed",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from exc
        return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Private — DB helpers
    # ------------------------------------------------------------------

    async def _get_profile(self, sub: uuid.UUID) -> Profile | None:
        result = await self.db.execute(
            select(Profile).where(Profile.id == sub),
        )
        return result.scalar_one_or_none()

    async def _create_profile_and_character(
        self,
        sub: uuid.UUID,
        email: str,
        name: str,
    ) -> Profile:
        """Create Profile, default Character, and Conversation in one transaction."""
        mem0_user_id = f"user_{sub}"
        mem0_agent_id = f"companion_{sub}"

        profile = Profile(
            id=sub,
            email=email,
            name=name,
            mem0_user_id=mem0_user_id,
            timezone="UTC",
            preferred_language="en",
            onboarding_completed=False,
            subscription_tier="free",
        )
        self.db.add(profile)

        character = Character(
            id=uuid.uuid4(),
            user_id=sub,
            name="Ember",
            template="companion",
            description=None,
            system_prompt=DEFAULT_COMPANION_PROMPT.format(user_name=name),
            mem0_agent_id=mem0_agent_id,
            avatar_style="default",
            is_default=True,
            is_active=True,
        )
        self.db.add(character)

        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=sub,
            character_id=character.id,
            last_message_at=None,
        )
        self.db.add(conversation)

        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    # ------------------------------------------------------------------
    # Private — misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_sub(id_token: str) -> uuid.UUID:
        """Decode the Cognito ID token (without JWKS verification) to get ``sub``."""
        claims = jwt.get_unverified_claims(id_token)
        return uuid.UUID(str(claims["sub"]))

    async def _authenticate_and_create_profile(
        self,
        email: str,
        password: str,
        name: str,
    ) -> AuthResponse:
        """Authenticate via Cognito and create DB profile if missing."""
        auth_result = await self._cognito_initiate_auth(email, password)

        id_token: str = auth_result["AuthenticationResult"]["IdToken"]
        refresh_token: str = auth_result["AuthenticationResult"]["RefreshToken"]
        sub = self._extract_sub(id_token)

        # Check if profile already exists (idempotent recovery)
        profile = await self._get_profile(sub)
        if profile is None:
            profile = await self._create_profile_and_character(sub, email, name)

        return AuthResponse(
            token=id_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(profile),
        )

    async def _handle_existing_cognito_user(
        self,
        email: str,
        password: str,
        name: str,
    ) -> AuthResponse:
        """Handle UsernameExistsException during registration.

        Attempts to authenticate. If the user can authenticate and has no
        profile in the DB, creates the missing profile (idempotent recovery
        for the Cognito-DB split-brain scenario). If the password is wrong
        the user truly already exists and we return a 400.
        """
        try:
            return await self._authenticate_and_create_profile(
                email, password, name,
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="An account with this email already exists",
                ) from exc
            raise

    @staticmethod
    def _raise_cognito_error(code: str) -> None:  # noqa: ANN401
        """Map a Cognito error code to the appropriate HTTPException."""
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password does not meet requirements",
            )
        if code == "InvalidParameterException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request parameters",
            )
        if code == "TooManyRequestsException":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, please try again later",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
