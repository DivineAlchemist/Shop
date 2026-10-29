"""Validated image uploads, stored under UPLOAD_FOLDER and served from /media/<path>."""
import os
import uuid
from urllib.parse import urlparse
from flask import current_app, url_for
from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {'PNG': 'png', 'JPEG': 'jpg', 'GIF': 'gif', 'WEBP': 'webp', 'ICO': 'ico'}


class UploadError(ValueError):
    pass


def save_image(file_storage, subdir='products', allow_ico=False):
    """Validate content with Pillow (never trust the filename/mimetype) and store under a random name."""
    if not file_storage or not getattr(file_storage, 'filename', ''):
        raise UploadError('No file selected.')
    try:
        img = Image.open(file_storage.stream)
        img.verify()  # detects truncated/corrupt files
        fmt = img.format
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise UploadError('Upload is not a valid image.')
    if fmt not in ALLOWED_FORMATS or (fmt == 'ICO' and not allow_ico):
        raise UploadError('Unsupported image type (use PNG, JPG, GIF or WEBP).')
    if img.width * img.height > 40_000_000:
        raise UploadError('Image dimensions are too large.')
    file_storage.stream.seek(0)
    name = f'{uuid.uuid4().hex}.{ALLOWED_FORMATS[fmt]}'
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], subdir)
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, name))
    return url_for('media', path=f'{subdir}/{name}')


def validate_image_url(url):
    """Accept http(s) URLs or our own /media paths for externally hosted/previously uploaded images."""
    url = (url or '').strip()
    if not url:
        return ''
    if len(url) > 400:
        raise UploadError('Image URL is too long.')
    if url.startswith('/media/'):
        return url
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.netloc:
        raise UploadError('Image URL must start with http:// or https://')
    return url
