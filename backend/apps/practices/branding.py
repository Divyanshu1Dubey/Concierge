"""
Practice branding: image processing for logos/team photos and the public brand payload
used by the website widget, patient emails and patient pages.
"""
import hashlib
import io
from urllib.parse import urlparse

from django.conf import settings

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED_FORMATS = {'PNG', 'JPEG', 'WEBP', 'GIF'}
SOCIAL_KEYS = ('website', 'instagram', 'facebook', 'google_reviews')


class ImageError(ValueError):
    pass


def _open(upload):
    from PIL import Image, ImageOps
    if upload is None:
        raise ImageError('Choose an image file to upload.')
    if getattr(upload, 'size', 0) > MAX_UPLOAD_BYTES:
        raise ImageError('That image is larger than 5 MB. Please use a smaller file.')
    data = upload.read()
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
        img = Image.open(io.BytesIO(data))
    except Exception:
        raise ImageError('That file is not a supported image. Please upload a PNG, JPG or WebP file.')
    if fmt not in ALLOWED_FORMATS:
        raise ImageError('Please upload a PNG, JPG or WebP image.')
    if img.width * img.height > MAX_PIXELS:
        raise ImageError('That image is too large. Please use one under 40 megapixels.')
    img = ImageOps.exif_transpose(img)
    return img


def process_logo(upload):
    """Fit within 480x160, keep transparency, store as PNG (metadata removed by re-encoding)."""
    img = _open(upload)
    img = img.convert('RGBA')
    img.thumbnail((480, 160))
    out = io.BytesIO()
    img.save(out, format='PNG', optimize=True)
    return out.getvalue(), 'image/png', img.width, img.height


def process_photo(upload):
    """Center-crop to a square and store a 320x320 JPEG."""
    from PIL import Image, ImageOps
    img = _open(upload)
    if img.mode in ('RGBA', 'LA', 'P'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        rgba = img.convert('RGBA')
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    else:
        img = img.convert('RGB')
    img = ImageOps.fit(img, (320, 320), method=Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=85, optimize=True)
    return out.getvalue(), 'image/jpeg', 320, 320


def store_asset(practice, kind, processed):
    from .models import BrandAsset
    content, ctype, w, h = processed
    digest = hashlib.sha256(content).hexdigest()[:16]
    return BrandAsset.objects.create(practice=practice, kind=kind, content=content, content_type=ctype,
                                     digest=digest, width=w, height=h)


def public_base(request=None) -> str:
    base = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
    if not base and request is not None:
        base = request.build_absolute_uri('/').rstrip('/')
    return base


def asset_url(asset, request=None) -> str:
    if not asset:
        return ''
    ext = 'png' if asset.content_type == 'image/png' else 'jpg'
    return f"{public_base(request)}/api/v1/brand-assets/{asset.id}/{asset.digest}.{ext}"


def clean_link(value: str) -> str:
    """Accept only http(s) links (no javascript:, data:, etc.)."""
    import re
    value = (value or '').strip()[:300]
    if not value:
        return ''
    error = 'Enter a full web address, for example https://instagram.com/yourpractice'
    if re.match(r'^[a-z][a-z0-9+.-]*:', value, re.I) and not value.lower().startswith(('http://', 'https://')):
        raise ValueError(error)  # javascript:, data:, mailto: ...
    if not value.lower().startswith(('http://', 'https://')):
        value = 'https://' + value
    parsed = urlparse(value)
    host = parsed.hostname or ''
    if parsed.scheme not in ('http', 'https') or ' ' in value or '.' not in host or not re.match(r'^[a-z0-9.-]+$', host, re.I):
        raise ValueError(error)
    return value


def social_links(practice) -> dict:
    ps = getattr(practice, 'settings', None)
    raw = (getattr(ps, 'social_links', None) or {}) if ps is not None else {}
    links = {k: raw.get(k) for k in SOCIAL_KEYS if isinstance(raw.get(k), str) and raw.get(k).startswith(('http://', 'https://'))}
    if 'website' not in links and practice.website:
        links['website'] = practice.website
    return links


def doctors_payload(practice, request=None, with_bio=True):
    out = []
    for d in practice.doctors.filter(is_active=True).select_related('photo')[:8]:
        row = {'id': d.id, 'name': d.name, 'credentials': d.credentials, 'photo_url': asset_url(d.photo, request)}
        if with_bio:
            row['bio'] = d.bio
        out.append(row)
    return out