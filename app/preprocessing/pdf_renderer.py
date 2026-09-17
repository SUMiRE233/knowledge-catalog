from pathlib import Path

import fitz
from PIL import Image, ImageEnhance, ImageOps

from app.models import PreparedPage, ServiceError


def enhance_page(path: Path) -> None:
    with Image.open(path) as image:
        corrected = ImageOps.exif_transpose(image)
        corrected = ImageOps.autocontrast(corrected.convert("RGB"), cutoff=1)
        corrected = ImageEnhance.Sharpness(corrected).enhance(1.12)
        corrected.save(path, "PNG")


def render_pdf(
    source: Path, pages_dir: Path, dpi: int, enhance_images: bool
) -> tuple[list[PreparedPage], bool]:
    try:
        document = fitz.open(source)
    except Exception as exc:
        raise ServiceError("INVALID_PDF", "PDF 无法打开或已损坏") from exc
    try:
        if document.needs_pass:
            raise ServiceError("ENCRYPTED_PDF", "不支持加密 PDF")
        if document.page_count < 1:
            raise ServiceError("INVALID_PDF", "PDF 没有页面")
        pages_dir.mkdir(parents=True, exist_ok=True)
        pages: list[PreparedPage] = []
        has_text = False
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for index, page in enumerate(document):
            auxiliary_text = page.get_text("text").strip()
            has_text = has_text or bool(auxiliary_text)
            target = pages_dir / f"page_{index + 1:04d}.png"
            page.get_pixmap(matrix=matrix, alpha=False).save(target)
            if enhance_images:
                enhance_page(target)
            pages.append(
                PreparedPage(
                    page_number=index + 1,
                    image_path=target,
                    auxiliary_text=auxiliary_text or None,
                )
            )
        return pages, has_text
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError("INVALID_PDF", "PDF 页面读取失败") from exc
    finally:
        document.close()
