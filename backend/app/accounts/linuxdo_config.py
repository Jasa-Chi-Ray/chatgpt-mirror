import os
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured


def load_linuxdo(local_network_access):
    mode = os.environ.get('LINUXDO_OAUTH_ENABLED', 'disable').strip().lower()
    if mode not in ('enable', 'disable'):
        raise ImproperlyConfigured('LINUXDO_OAUTH_ENABLED must be enable or disable')
    enabled = mode == 'enable'
    client_id = os.environ.get('LINUXDO_CLIENT_ID', '').strip()
    secret = os.environ.get('LINUXDO_CLIENT_SECRET', '').strip()
    redirect = os.environ.get('LINUXDO_REDIRECT_URI', '').strip()
    try:
        minimum = int(os.environ.get('LINUXDO_MIN_TRUST_LEVEL', '0'))
        if minimum not in range(5):
            raise ValueError
    except ValueError:
        raise ImproperlyConfigured('LINUXDO_MIN_TRUST_LEVEL must be between 0 and 4') from None
    if enabled:
        if not all((client_id, secret, redirect)):
            raise ImproperlyConfigured('Linux DO OAuth requires client id, client secret and redirect URI')
        try:
            parsed = urlsplit(redirect)
            parsed.port
        except ValueError:
            raise ImproperlyConfigured('LINUXDO_REDIRECT_URI is invalid') from None
        if (parsed.scheme not in (('https', 'http') if local_network_access else ('https',))
                or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path != '/0x/user/oauth/linuxdo/callback' or any(c.isspace() for c in redirect)):
            raise ImproperlyConfigured('LINUXDO_REDIRECT_URI must be a fixed /0x/user/oauth/linuxdo/callback URL; HTTP is only available in local network mode')
    return enabled, client_id, secret, redirect, minimum
