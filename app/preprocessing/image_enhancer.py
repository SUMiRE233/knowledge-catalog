from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

from app.models import ServiceError


def prepare_image(source: Path, target: Path, enhance: bool) -> None:
    try:
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            prepared = ImageOps.exif_transpose(image).convert("RGB")
            if enhance:
                prepared = ImageOps.autocontrast(prepared, cutoff=1)
                prepared = ImageEnhance.Sharpness(prepared).enhance(1.08)
            target.parent.mkdir(parents=True, exist_ok=True)
            prepared.save(target, "PNG")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ServiceError("INVALID_IMAGE", "图片无法解码") from exc
