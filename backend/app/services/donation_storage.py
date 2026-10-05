from pathlib import Path
import uuid

from app.core.config import get_settings


class LocalDonationStorage:
    """Local development storage, replaceable with an object storage adapter."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(get_settings().upload_dir)

    def save(self, content: bytes, suffix: str) -> str:
        key = f"{uuid.uuid4().hex}{suffix}"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / key).write_bytes(content)
        return key

    def read(self, key: str) -> bytes:
        if Path(key).name != key:
            raise FileNotFoundError(key)
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            (self.root / key).unlink(missing_ok=True)
        except OSError:
            pass
