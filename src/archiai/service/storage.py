"""Where generated files go. Local disk for development, Supabase Storage in
production; the API surface is identical either way."""

import os
import httpx

from .config import settings


class Stored:
    __slots__ = ("key", "url", "size", "content_type")

    def __init__(self, key, url, size, content_type):
        self.key, self.url, self.size, self.content_type = key, url, size, content_type

    def as_dict(self):
        return {"key": self.key, "url": self.url, "bytes": self.size,
                "content_type": self.content_type}


class Storage:
    async def put(self, key, data, content_type):
        raise NotImplementedError


class LocalStorage(Storage):
    """Writes under a root and serves the files back through the app itself."""

    def __init__(self, root, public_base=""):
        self.root, self.public_base = root, public_base.rstrip("/")

    async def put(self, key, data, content_type):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        base = self.public_base or ""
        return Stored(key, "%s/files/%s" % (base, key), len(data), content_type)


class SupabaseStorage(Storage):
    """Uploads through the Storage REST API with the service role key.

    The key is only ever used server side; it never reaches a browser."""

    def __init__(self, url, key, bucket, public=True, timeout=30.0):
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when "
                "ARCHIAI_STORAGE=supabase")
        self.url, self.key, self.bucket = url.rstrip("/"), key, bucket
        self.public, self.timeout = public, timeout

    async def put(self, key, data, content_type):
        endpoint = "%s/storage/v1/object/%s/%s" % (self.url, self.bucket, key)
        headers = {"Authorization": "Bearer %s" % self.key,
                   "Content-Type": content_type,
                   "x-upsert": "true",
                   "cache-control": "public, max-age=31536000, immutable"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(endpoint, content=data, headers=headers)
        if r.status_code not in (200, 201):
            raise RuntimeError("upload of %s failed: %s %s"
                               % (key, r.status_code, r.text[:300]))
        if self.public:
            url = "%s/storage/v1/object/public/%s/%s" % (self.url, self.bucket, key)
        else:
            url = "%s/%s" % (self.bucket, key)          # caller signs it
        return Stored(key, url, len(data), content_type)


def make_storage():
    if settings.backend == "supabase":
        return SupabaseStorage(settings.supabase_url, settings.supabase_key,
                               settings.supabase_bucket, settings.supabase_public,
                               settings.request_timeout)
    return LocalStorage(settings.local_root, settings.public_base)
