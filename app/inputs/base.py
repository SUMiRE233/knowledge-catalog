
from app.config import Settings
from app.models import GenerationOptions, PreparedDocument, ServiceError, StoredFile
from app.preprocessing.image_enhancer import prepare_image
from app.preprocessing.pdf_renderer import render_pdf

PDF_MAGIC = b"%PDF-"
IMAGE_MAGICS = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}


class InputAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def prepare(self, stored: StoredFile, options: GenerationOptions) -> PreparedDocument:
        head = stored.path.read_bytes()[:16]
        pages_dir = stored.path.parent.parent / "prepared" / "pages"
        suffix = stored.path.suffix.lower()
        is_pdf_claim = stored.content_type == "application/pdf" or suffix == ".pdf"
        if is_pdf_claim:
            if not head.startswith(PDF_MAGIC):
                raise ServiceError("INVALID_PDF", "文件不含有效 PDF 标识")
            pages, has_text = render_pdf(
                stored.path,
                pages_dir,
                self.settings.pdf_render_dpi,
                options.enhance_images,
            )
            return PreparedDocument(
                source_file_name=stored.original_filename,
                input_type="standard_pdf" if has_text else "scanned_pdf",
                pages=pages,
            )

        claimed = stored.content_type
        if claimed not in self.settings.allowed_image_types:
            raise ServiceError("INVALID_FILE_TYPE", "仅支持 PDF、PNG、JPEG 和 WEBP")
        expected = IMAGE_MAGICS.get(claimed, ())
        if not expected or not any(head.startswith(magic) for magic in expected):
            raise ServiceError("INVALID_IMAGE", "图片内容与声明类型不一致")
        if claimed == "image/webp" and head[8:12] != b"WEBP":
            raise ServiceError("INVALID_IMAGE", "WEBP 文件标识无效")
        target = pages_dir / "page_0001.png"
        prepare_image(stored.path, target, options.enhance_images)
        return PreparedDocument(
            source_file_name=stored.original_filename,
            input_type="image",
            pages=[{"page_number": 1, "image_path": target, "auxiliary_text": None}],
        )
