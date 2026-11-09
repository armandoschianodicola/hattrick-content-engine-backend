import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from hattrick_backend.core.exceptions import AppError


class AssetStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...


class LocalAssetStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise AppError("invalid_asset_path", "Invalid asset key", 400)
        return path

    def put(self, key, data):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise AppError("asset_not_found", "Asset file is unavailable", 404) from None
