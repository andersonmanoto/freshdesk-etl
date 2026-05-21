from functools import lru_cache

from supabase import Client, create_client

from config.settings import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Retorna uma instância singleton do client Supabase."""
    return create_client(settings.supa_url, settings.supa_key)
