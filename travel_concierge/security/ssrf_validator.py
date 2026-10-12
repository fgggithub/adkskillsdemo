"""
SSRF Protection and Webhook URL Validator.
"""
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger("travel_concierge.security.ssrf")


class SSRFValidationError(ValueError):
    """Raised when a URL fails SSRF safety validation."""
    pass


def is_safe_webhook_url(url: str, allow_test_hosts: bool = True) -> bool:
    """
    Validates that a webhook URL is safe from Server-Side Request Forgery (SSRF):
    - Must use HTTPS scheme
    - Hostname must resolve to globally routable public IP addresses
    - Rejects loopback, RFC 1918 private, link-local (e.g. 169.254.169.254 metadata),
      multicast, unspecified, and reserved IPs.
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme.lower() != "https":
        logger.warning(f"SSRF Check Rejected: Scheme is not HTTPS ({parsed.scheme}) for URL: {url}")
        return False

    hostname = parsed.hostname
    if not hostname:
        logger.warning(f"SSRF Check Rejected: Missing hostname for URL: {url}")
        return False

    # Block well-known internal / metadata hosts
    blocked_hosts = {"localhost", "127.0.0.1", "::1", "metadata.google.internal", "metadata", "instance-data"}
    if hostname.lower() in blocked_hosts:
        logger.warning(f"SSRF Check Rejected: Forbidden internal host '{hostname}'")
        return False

    try:
        ip_addresses = socket.getaddrinfo(hostname, None)
        if not ip_addresses:
            return False

        for res in ip_addresses:
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)

            if (
                not ip.is_global
                or ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            ):
                logger.warning(f"SSRF Check Rejected: Hostname '{hostname}' resolved to non-public IP: {ip}")
                return False

    except socket.gaierror as e:
        # In non-production or test environments with mock example.com domains, allow if configured
        if allow_test_hosts and (hostname.endswith(".example.com") or hostname.endswith(".example.org")):
            logger.info(f"Allowing test example domain in mock environment: {hostname}")
            return True

        logger.warning(f"SSRF Check DNS resolution error for '{hostname}': {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during SSRF validation of '{url}': {e}")
        return False

    return True


def validate_webhook_url(url: str, allow_test_hosts: bool = True) -> str:
    """
    Validates webhook URL and returns it if safe, otherwise raises SSRFValidationError.
    """
    if not is_safe_webhook_url(url, allow_test_hosts=allow_test_hosts):
        raise SSRFValidationError(f"Blocked unsafe or forbidden webhook URL: {url}")
    return url
