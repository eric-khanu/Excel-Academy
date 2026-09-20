# id_cards/templatetags/__init__.py  (empty file)
# id_cards/templatetags/id_cards_extras.py

import re
from django import template

register = template.Library()

HEX_COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}){1,2}$')


@register.filter
def safe_hex(value, default="#8B2020"):
    """
    Return `value` if it's a valid hex color, else `default`.
    Prevents CSS injection via a malicious School.primary_color.
    """
    if isinstance(value, str) and HEX_COLOR_RE.match(value.strip()):
        return value.strip()
    return default


@register.filter
def in_csv(value, csv):
    """Return True if `value` is one of the comma-separated items in `csv`."""
    if value is None:
        return False
    items = [v.strip() for v in str(csv).split(',') if v.strip()]
    return str(value) in items