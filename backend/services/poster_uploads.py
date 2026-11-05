import json
import shutil
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from backend.errors import ApiError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    mime_type: str
    extension: str


def validate_image(content: bytes, claimed_type: str | None) -> ValidatedImage:
    if len(content) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "포스터는 최대 5MB까지 업로드할 수 있습니다.")
    if claimed_type not in {mime for mime, _ in FORMATS.values()}:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "JPG, PNG, WebP 이미지만 업로드해 주세요.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                format_name = image.format
                if format_name not in FORMATS:
                    raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "지원하지 않는 이미지 형식입니다.")
                if FORMATS[format_name][0] != claimed_type:
                    raise ApiError(
                        400, "INVALID_IMAGE", "파일 내용과 이미지 형식이 일치하지 않습니다."
                    )
                if (
                    image.width * image.height > MAX_IMAGE_PIXELS
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ApiError(
                        400, "INVALID_IMAGE", "2,500만 화소 이하의 정지 이미지를 사용해 주세요."
                    )
                image.verify()
            # Signature/headers alone do not catch truncated image data.
            with Image.open(BytesIO(content)) as image:
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ApiError(400, "INVALID_IMAGE", "손상되었거나 읽을 수 없는 이미지입니다.") from error
    mime_type, extension = FORMATS[format_name]
    return ValidatedImage(content, mime_type, extension)


class PendingUploadStore:
    """Private, expiring uploads; registration owns final media movement and DB commit."""

    def __init__(self, root: Path, ttl_hours: int):
        self.root = root.resolve()
        self.ttl_seconds = ttl_hours * 3600

    def save(self, image: ValidatedImage) -> str:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        upload_id = str(uuid4())
        directory = self.root / upload_id
        directory.mkdir(mode=0o700)
        try:
            path = directory / f"poster{image.extension}"
            path.write_bytes(image.content)
            path.chmod(0o600)
            metadata = {
                "filename": path.name,
                "mime_type": image.mime_type,
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        except BaseException:
            shutil.rmtree(directory)
            raise
        return upload_id

    def resolve(self, upload_id: str) -> Path:
        """Registration handoff: validate UUID/expiry, then claim in its own transaction."""
        try:
            if str(UUID(upload_id)) != upload_id:
                raise ValueError()
            directory = self.root / upload_id
            if directory.is_symlink() or time.time() - directory.stat().st_mtime > self.ttl_seconds:
                raise ValueError()
            paths = [directory / f"poster{extension}" for _, extension in FORMATS.values()]
            matches = [path for path in paths if path.is_file() and not path.is_symlink()]
            if len(matches) != 1:
                raise ValueError()
            return matches[0]
        except (ValueError, OSError) as error:
            raise ApiError(
                422, "INVALID_UPLOAD", "업로드가 없거나 만료되었습니다. 다시 업로드해 주세요."
            ) from error

    def cleanup(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.iterdir():
            try:
                if str(UUID(path.name)) != path.name or path.is_symlink() or not path.is_dir():
                    continue
                if time.time() - path.stat().st_mtime > self.ttl_seconds:
                    shutil.rmtree(path)
            except (ValueError, FileNotFoundError):
                continue
