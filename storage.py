"""Files that don't belong in the sheet: receipt photos, downloaded fund data, look-through history.

They go in the private bucket set in config.BUCKET (deploy.sh does that on Cloud Run), or in this folder
when there is none (files/, git-ignored). Same names either way:

    receipts/<name>        receipt photos and PDFs
    lookthrough/<date>.json   one look-through result per day
    cache/…                downloads (prices, fund holdings), replaced every day

Keys use "/" and never start with one.
"""
from datetime import datetime
from pathlib import Path

import config

HERE = Path(__file__).parent


class Folder:
    """Files under a folder on disk."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, key):
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"bad key: {key!r}")
        return path

    def read(self, key):
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def write(self, key, data, content_type=None):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    def keys(self, prefix):
        base = self._path(prefix.rstrip("/"))
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file()) if base.is_dir() else []


class Bucket:
    """Files in a Google Cloud Storage bucket, with the service account's (or your gcloud) credentials."""

    def __init__(self, name):
        from google.cloud import storage  # only needed when there is a bucket
        # quota_project: bill this project even on your computer, whatever gcloud's default project is
        options = {"quota_project_id": config.PROJECT} if config.PROJECT else None
        self.bucket = storage.Client(project=config.PROJECT or None, client_options=options).bucket(name)

    def read(self, key):
        from google.api_core.exceptions import NotFound
        try:
            return self.bucket.blob(key).download_as_bytes()
        except NotFound:
            return None

    def write(self, key, data, content_type=None):
        self.bucket.blob(key).upload_from_string(data, content_type=content_type or "application/octet-stream")

    def delete(self, key):
        from google.api_core.exceptions import NotFound
        try:
            self.bucket.blob(key).delete()
        except NotFound:
            pass

    def keys(self, prefix):
        return sorted(b.name for b in self.bucket.client.list_blobs(self.bucket, prefix=prefix))


_store = Bucket(config.BUCKET) if config.BUCKET else Folder(HERE / "files")
read, write, delete, keys = _store.read, _store.write, _store.delete, _store.keys


def cached_download(folder, name, fetch):
    """fetch() once per calendar day: the result is kept as cache/<folder>/<YYYYMMDD>_<name>
    (older days of the same name are deleted). Returns bytes."""
    key = f"cache/{folder}/{datetime.now():%Y%m%d}_{name}"
    body = read(key)
    if body is None:
        for old in keys(f"cache/{folder}/"):
            if old.endswith(f"_{name}"):
                delete(old)
        body = fetch()
        write(key, body)
    return body

