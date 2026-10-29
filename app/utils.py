import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

_PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def slugify(text: str) -> str:
    text = re.sub(r'[^\w\s-]', '', text or '').strip().lower()
    return re.sub(r'[-\s]+', '-', text)


def unique_slug(model, base, exclude_id=None, field='slug', max_len=80):
    """Return a slug not used by any other row of `model`."""
    base = (slugify(base) or 'item')[:max_len - 6]
    slug, i = base, 1
    col = getattr(model, field)
    while True:
        q = model.query.filter(col == slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if not db_exists(q):
            return slug
        i += 1
        slug = f'{base}-{i}'


def db_exists(query):
    return query.first() is not None


def safe_next_url(target):
    """Only allow same-site relative redirects (prevents open redirects)."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return None
    return target


def normalize_phone(raw):
    """Normalise Iranian-style mobile numbers to 09XXXXXXXXX; return None when invalid."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw).translate(_PERSIAN_DIGITS))
    if digits.startswith('0098'):
        digits = '0' + digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    if re.fullmatch(r'09\d{9}', digits):
        return digits
    return None


def to_decimal(value, default=None):
    if value is None or str(value).strip() == '':
        return default
    try:
        d = Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return default
    return d if d.is_finite() else default


def escape_like(term):
    return term.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')
