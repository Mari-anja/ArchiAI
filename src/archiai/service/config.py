"""Environment-driven settings. Nothing here is secret at import time."""

import os


def _bool(name, default=False):
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    def __init__(self):
        self.api_keys = [k.strip() for k in
                         os.environ.get("ARCHIAI_API_KEYS", "").split(",") if k.strip()]
        self.allow_anonymous = _bool("ARCHIAI_ALLOW_ANONYMOUS", not self.api_keys)
        self.backend = os.environ.get("ARCHIAI_STORAGE", "local").strip().lower()
        self.local_root = os.path.abspath(
            os.environ.get("ARCHIAI_LOCAL_ROOT", "/tmp/archiai-output"))
        self.public_base = os.environ.get("ARCHIAI_PUBLIC_BASE", "").rstrip("/")
        self.supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.supabase_bucket = os.environ.get("SUPABASE_BUCKET", "building-projects")
        self.supabase_public = _bool("SUPABASE_BUCKET_PUBLIC", True)
        self.max_storeys = int(os.environ.get("ARCHIAI_MAX_STOREYS", "60"))
        self.max_area = float(os.environ.get("ARCHIAI_MAX_AREA_M2", "400000"))
        self.request_timeout = float(os.environ.get("ARCHIAI_UPLOAD_TIMEOUT", "30"))

    def describe(self):
        return {"storage": self.backend,
                "auth": "open" if self.allow_anonymous else "bearer",
                "bucket": self.supabase_bucket if self.backend == "supabase" else None}


settings = Settings()
