"""Load the last host-side credential check without making login depend on a network request."""

import json
import time
from pathlib import Path

from yishan_id.oidc import OIDCError, Settings, validate_settings


def load(path, *, require_verified):
	try:
		data = json.loads(Path(path).read_text())
		if require_verified and not time.time() < data['verified_until']:
			return None
		values = {k: data[k] for k in ('issuer', 'redirect_uri', 'client_id', 'client_secret')}
		if not all(isinstance(v, str) and v.strip() for v in values.values()):
			return None
		settings = Settings(**values)
		validate_settings(settings)
		return settings
	except (OSError, ValueError, TypeError, KeyError, OIDCError):
		return None
