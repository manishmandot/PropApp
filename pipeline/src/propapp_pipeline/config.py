import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    supabase_url: str
    supabase_service_role_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [k for k in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
                   if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
        return cls(
            database_url=os.environ["DATABASE_URL"],
            supabase_url=os.environ["SUPABASE_URL"].rstrip("/"),
            supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
