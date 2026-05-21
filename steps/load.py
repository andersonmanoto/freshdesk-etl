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
        logger.warning(
            "[State] Não foi possível ler etl_state: {}. Usando data inicial.", exc
        )

    logger.info(
        "[State] Nenhum estado anterior — usando initial_sync_date: {}",
        settings.initial_sync_date,
    )
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
    Faz upsert dos tickets no Supabase em chunks.
    Garante que nenhum ticket apareça duas vezes no mesmo chunk para
    evitar o erro 21000, preservando todo o histórico na Trigger.
    """
    if not payload:
        logger.info("[Load] Payload vazio — nada a carregar.")
        return

    supabase = get_supabase()

    # 1. Ordenar o payload do mais antigo para o mais novo (Cronologia)
    # Isso garante que a Trigger do banco bata na ordem certa e grave o histórico perfeitamente
    payload_sorted = sorted(payload, key=lambda x: x["fd_updated_at"])

    # 2. Separação em Lotes Inteligentes (Garantindo UNICIDADE por lote)
    chunk_size = settings.upsert_chunk_size
    batches = []
    seen_in_batches = []  # Lista de conjuntos (sets) para controle super rápido na memória

    for row in payload_sorted:
        ticket_id = row["freshdesk_ticket_id"]
        placed = False

        # Tenta encaixar o ticket no primeiro lote que ainda NÃO o contenha
        for i, batch in enumerate(batches):
            if len(batch) < chunk_size and ticket_id not in seen_in_batches[i]:
                batch.append(row)
                seen_in_batches[i].add(ticket_id)
                placed = True
                break

        # Se todos os lotes já contêm esse ticket ou estão cheios, cria um lote novo
        if not placed:
            batches.append([row])
            seen_in_batches.append({ticket_id})

    total_chunks = len(batches)
    logger.info(
        "[Load] Iniciando upsert de {} tickets em {} chunk(s) (Lotes Seguros)...",
        len(payload_sorted),
        total_chunks,
    )

    # 3. Dispara os Lotes para o banco em ordem
    for i, chunk in enumerate(batches, start=1):
        try:
            supabase.table("cs_tickets").upsert(
                chunk,
                on_conflict="freshdesk_ticket_id,fd_created_at",
            ).execute()
            logger.debug(
                "[Load] Chunk {}/{} concluído ({} rows).", i, total_chunks, len(chunk)
            )
        except Exception as exc:
            logger.error(
                "[Load] Falha no chunk {}/{} (Tamanho: {}): {}",
                i,
                total_chunks,
                len(chunk),
                exc,
            )
            raise

    logger.info(
        "[Load] Upsert finalizado — {} registros carregados.", len(payload_sorted)
    )
