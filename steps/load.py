"""
Etapa L (Load):
  - Upsert em chunks para evitar timeouts com volumes grandes
  - Controle de estado (last_run) persistido no Supabase (tabela etl_state)
"""

from loguru import logger

from config.settings import settings
from services.supabase_client import get_supabase

_STATE_KEY = "freshdesk_last_run"


# ---------------------------------------------------------------------------
# Controle de estado
# ---------------------------------------------------------------------------

def get_last_run() -> str:
    """
    Lê a data da última execução bem-sucedida da tabela `etl_state`.
    Retorna `settings.initial_sync_date` se ainda não houver registro.
    """
    supabase = get_supabase()
    try:
        res = (
            supabase.table("etl_state")
            .select("value")
            .eq("key", _STATE_KEY)
            .maybe_single()
            .execute()
        )
        if res.data:
            logger.debug("[State] last_run carregado: {}", res.data["value"])
            return res.data["value"]
    except Exception as exc:
        logger.warning("[State] Não foi possível ler etl_state: {}. Usando data inicial.", exc)

    logger.info("[State] Nenhum estado anterior — usando initial_sync_date: {}", settings.initial_sync_date)
    return settings.initial_sync_date


def save_last_run(timestamp: str) -> None:
    """Persiste o timestamp da última execução na tabela `etl_state`."""
    if not timestamp:
        logger.warning("[State] Timestamp vazio — estado não atualizado.")
        return

    supabase = get_supabase()
    try:
        supabase.table("etl_state").upsert(
            {"key": _STATE_KEY, "value": timestamp},
            on_conflict="key",
        ).execute()
        logger.info("[State] last_run salvo: {}", timestamp)
    except Exception as exc:
        logger.error("[State] Falha ao salvar last_run: {}", exc)
        raise


# ---------------------------------------------------------------------------
# Upsert em chunks
# ---------------------------------------------------------------------------

def load_tickets(payload: list[dict]) -> None:
    """
    Faz upsert dos tickets no Supabase em chunks de `settings.upsert_chunk_size`.
    O on_conflict usa apenas freshdesk_ticket_id (constraint única) para garantir
    que updates em tickets existentes funcionem corretamente.
    """
    if not payload:
        logger.info("[Load] Payload vazio — nada a carregar.")
        return

    supabase = get_supabase()
    chunk_size = settings.upsert_chunk_size
    total = len(payload)
    total_chunks = (total + chunk_size - 1) // chunk_size

    logger.info("[Load] Iniciando upsert de {} tickets em {} chunk(s)...", total, total_chunks)

    for i, start in enumerate(range(0, total, chunk_size), start=1):
        chunk = payload[start : start + chunk_size]
        try:
            supabase.table("cs_tickets").upsert(
                chunk,
                on_conflict="freshdesk_ticket_id,fd_created_at",
            ).execute()
            logger.debug("[Load] Chunk {}/{} concluído ({} rows).", i, total_chunks, len(chunk))
        except Exception as exc:
            logger.error(
                "[Load] Falha no chunk {}/{} (rows {} a {}): {}",
                i, total_chunks, start, start + len(chunk) - 1, exc,
            )
            raise

    logger.info("[Load] Upsert finalizado — {} tickets carregados.", total)
