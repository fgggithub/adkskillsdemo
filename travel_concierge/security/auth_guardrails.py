"""
IAM Group, OAuth 2.0 Scope validation decorators and Agent Gateway Zero Trust utilities.
"""
import functools
import logging
from typing import Callable, Dict, Any, Optional
from travel_concierge.telemetry.tracer import inject_trace_context

logger = logging.getLogger("travel_concierge.auth")


def require_mcp_group_membership(required_group: str = "MCPUSERS") -> Callable:
    """
    Decorator enforcing IAM group membership in caller's security claims.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Inspect first positional arg or token_claims kwarg
            token_claims = kwargs.get("token_claims")
            if token_claims is None and args:
                if isinstance(args[0], dict) and ("groups" in args[0] or "sub" in args[0]):
                    token_claims = args[0]

            if not isinstance(token_claims, dict):
                raise PermissionError("403 Forbidden: Missing security token claims.")

            user_groups = token_claims.get("groups", [])
            if isinstance(user_groups, str):
                user_groups = [user_groups]

            if required_group not in user_groups:
                logger.warning(
                    f"Access denied: Subject '{token_claims.get('sub')}' missing required group '{required_group}'"
                )
                raise PermissionError(
                    f"403 Forbidden: User not in group '{required_group}'."
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_oauth_scope(required_scope: str) -> Callable:
    """
    Decorator enforcing required OAuth 2.0 scopes in caller's token claims.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            token_claims = kwargs.get("token_claims")
            if token_claims is None and args:
                if isinstance(args[0], dict) and ("scope" in args[0] or "scopes" in args[0]):
                    token_claims = args[0]

            if not isinstance(token_claims, dict):
                raise PermissionError("403 Forbidden: Missing security token claims.")

            granted_scopes = token_claims.get("scope", "")
            if isinstance(granted_scopes, str):
                scope_set = set(granted_scopes.split(" "))
            elif isinstance(granted_scopes, list):
                scope_set = set(granted_scopes)
            else:
                scope_set = set()

            if required_scope not in scope_set:
                logger.warning(
                    f"Access denied: Subject '{token_claims.get('sub')}' missing scope '{required_scope}'"
                )
                raise PermissionError(
                    f"403 Forbidden: Missing scope '{required_scope}'."
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator


def build_gateway_headers(
    caller_spiffe_gateway_token: Optional[str] = None,
    target_subagent_access_token: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Builds Agent Gateway Zero-Trust headers:
    1. W3C Trace Context (OpenTelemetry)
    2. Proxy-Authorization & X-Proxy-Authorization: Caller's Agent Identity / SPIFFE token for PEP policy verification
    3. Authorization: Audience-bound token for downstream target subagent
    """
    headers = dict(extra_headers or {})
    inject_trace_context(headers)

    if caller_spiffe_gateway_token:
        headers["Proxy-Authorization"] = f"Bearer {caller_spiffe_gateway_token}"
        headers["X-Proxy-Authorization"] = f"Bearer {caller_spiffe_gateway_token}"
        headers["X-Caller-Identity"] = f"Bearer {caller_spiffe_gateway_token}"

    if target_subagent_access_token:
        headers["Authorization"] = f"Bearer {target_subagent_access_token}"

    return headers


def extract_token_claims(token: str) -> Dict[str, Any]:
    """
    Extracts payload claims from JWT token string without requiring verification secret.
    Inspects standard payload part and falls back gracefully.
    """
    if not token:
        return {}
    if token.startswith("Bearer "):
        token = token[7:].strip()
    parts = token.split(".")
    for idx in ((1, 0) if len(parts) >= 2 else (0,)):
        if idx < len(parts):
            try:
                import base64
                import json
                b64 = parts[idx]
                rem = len(b64) % 4
                if rem > 0:
                    b64 += "=" * (4 - rem)
                decoded = base64.urlsafe_b64decode(b64.encode("utf-8"))
                claims = json.loads(decoded.decode("utf-8"))
                if isinstance(claims, dict) and any(k in claims for k in ("aud", "sub", "iss", "groups", "scope")):
                    return claims
            except Exception:
                continue
    return {}


def validate_agent_gateway_headers(headers: Dict[str, str], expected_audience: Optional[str] = None) -> bool:
    """
    Validates presence and format of Agent Gateway authorization headers.
    When expected_audience is specified, validates that the target token in
    Authorization is audience-bound to the downstream agent.
    """
    proxy_auth = (
        headers.get("Proxy-Authorization")
        or headers.get("proxy-authorization")
        or headers.get("X-Proxy-Authorization")
        or headers.get("x-proxy-authorization")
        or headers.get("X-Caller-Identity")
        or headers.get("x-caller-identity")
    )
    auth = headers.get("Authorization") or headers.get("authorization")

    if not proxy_auth or not proxy_auth.startswith("Bearer "):
        logger.error("Missing or invalid Proxy-Authorization header.")
        return False

    if not auth or not auth.startswith("Bearer "):
        logger.error("Missing or invalid Authorization header.")
        return False

    if expected_audience:
        token = auth.split(" ", 1)[1].strip()
        claims = extract_token_claims(token)
        aud = claims.get("aud")
        if aud:
            if isinstance(aud, list):
                if expected_audience not in aud and not any(expected_audience in a or a in expected_audience for a in aud):
                    logger.error(f"Audience mismatch: expected '{expected_audience}', got {aud}")
                    return False
            elif aud != expected_audience and expected_audience not in aud and aud not in expected_audience:
                logger.error(f"Audience mismatch: expected '{expected_audience}', got '{aud}'")
                return False

    return True

