"""Image validation, normalisation, fingerprinting and watermark utilities."""
from __future__ import annotations
import hashlib, math, secrets, sqlite3
from io import BytesIO
from pathlib import Path
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

def perceptual_image_hash(image: Image.Image) -> str:
    """Low-frequency image fingerprint: tolerant of re-encoding and light watermarks."""
    gray = image.convert("L").resize((32, 32))
    pixels = list(gray.getdata())
    cosines = [[math.cos((2 * x + 1) * u * math.pi / 64) for x in range(32)] for u in range(8)]
    coefficients = []
    for v in range(8):
        for u in range(8):
            total = 0.0
            for y in range(32):
                row_offset = y * 32
                cy = cosines[v][y]
                for x in range(32):
                    total += pixels[row_offset + x] * cosines[u][x] * cy
            coefficients.append(total)
    values = coefficients[1:]
    median = sorted(values)[len(values) // 2]
    bits = "".join("1" if value > median else "0" for value in coefficients)
    return f"{int(bits, 2):016x}"


def perceptual_hash_from_bytes(raw: bytes) -> str:
    with Image.open(BytesIO(raw)) as source:
        safe = ImageOps.exif_transpose(source).convert("RGB")
        safe.thumbnail((1800, 1800))
        return perceptual_image_hash(safe)


def canonicalise_image(raw: bytes) -> tuple[bytes, str, str]:
    """Validate, normalize orientation/size, strip metadata, and fingerprint an image."""
    Image.MAX_IMAGE_PIXELS = 24_000_000
    try:
        with Image.open(BytesIO(raw)) as check:
            if check.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Use a JPG, PNG or WebP image.")
            check.verify()
        with Image.open(BytesIO(raw)) as source:
            safe = ImageOps.exif_transpose(source).convert("RGB")
            safe.thumbnail((1800, 1800))
            phash = perceptual_image_hash(safe)
            output = BytesIO()
            safe.save(output, format="JPEG", quality=88, optimize=True)
            normalized = output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=415, detail="The file is not a valid supported image.")
    return normalized, hashlib.sha256(normalized).hexdigest(), phash


def image_fingerprint_matches(conn: sqlite3.Connection, image_sha256: str, image_phash: str) -> bool:
    """Check exact hashes and visually near-identical photos across reports and claim evidence."""
    existing = conn.execute(
        """SELECT image_sha256, image_phash FROM reports WHERE image_path IS NOT NULL
           UNION ALL
           SELECT image_sha256, image_phash FROM claim_evidence_images"""
    ).fetchall()
    candidate = int(image_phash, 16)
    for row in existing:
        if row["image_sha256"] and secrets.compare_digest(str(row["image_sha256"]), image_sha256):
            return True
        if row["image_phash"]:
            try:
                if (candidate ^ int(row["image_phash"], 16)).bit_count() <= 4:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def watermark_image(path: Path, label: str) -> bytes:
    """Serve labelled previews to discourage saving/reusing photos as claim evidence."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    text = "LostLink - " + label
    bounds = draw.textbbox((0, 0), text, font=font)
    bar_height = max(30, bounds[3] - bounds[1] + 14)
    top = max(0, image.height - bar_height)
    draw.rectangle((0, top, image.width, image.height), fill=(18, 44, 42))
    draw.text((12, top + 6), text, font=font, fill=(255, 255, 255))
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()
