"""
Job 2: Snapshot Diário de Métricas de CS
Roda de madrugada para processar os tickets do dia anterior (D-1),
calculando taxas de retenção, volume e valor por agente.

Fluxo:
  1. Define data-alvo (D-1 por padrão, ou range via argumento)
  2. Extrai tickets do dia com paginação
  3. Agrega métricas por agente em memória
  4. Upsert em snapshot_daily_cs_agent

Uso:
  py jobs/job_daily_metrics.py              # processa D-1
  py jobs/job_daily_metrics.py 2026-05-01   # backfill de 01/05 até D-1
"""

import sys
from datetime import datetime, timedelta, timezone

from loguru import logger

from utils.logger import setup_logger
from services.supabase_client import get_supabase
from steps.aggregate import aggregate_by_agent

_SNAPSHOT_TABLE = "snapshot_daily_cs_agent"
_PAGE_SIZE = 1000


# ---------------------------------------------------------------------------
# Extração paginada
# ---------------------------------------------------------------------------

def _fetch_tickets_for_date(target_date: str) -> list[dict]:
    """
    Busca todos os tickets cujo fd_updated_at cai no target_date.
    Pagina em lotes de _PAGE_SIZE para não esbarrar no limite do PostgREST.
    Seleciona apenas as colunas necessárias para a agregação.
    """
    supabase = get_supabase()
    start = f"{target_date}T00:00:00Z"
    end   = f"{target_date}T23:59:59Z"

    logger.info("[Extract] Buscando tickets entre {} e {}...", start, end)

    all_tickets: list[dict] = []
    offset = 0

    while True:
        res = (
            supabase.table("cs_tickets")
            .select(
                "agent_id, status, ticket_type, "
                "retention_outcome, retention_step_id, retained_value"
            )
            .gte("fd_updated_at", start)
            .lte("fd_updated_at", end)
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )

        batch = res.data or []
        all_tickets.extend(batch)
        logger.debug("[Extract] Página offset={} → {} rows (total: {})", offset, len(batch), len(all_tickets))

        if len(batch) < _PAGE_SIZE:
            break

        offset += _PAGE_SIZE

    logger.info("[Extract] {} tickets encontrados para {}.", len(all_tickets), target_date)
    return all_tickets


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def _load_snapshot(payload: list[dict]) -> None:
    if not payload:
        logger.info("[Load] Payload vazio — nada a carregar.")
        return

    supabase = get_supabase()
    supabase.table(_SNAPSHOT_TABLE).upsert(
        payload,
        on_conflict="agent_id,snapshot_date",
    ).execute()
    logger.info("[Load] Upsert de {} snapshots concluído.", len(payload))


# ---------------------------------------------------------------------------
# Unidade de trabalho por data
# ---------------------------------------------------------------------------

def process_date(target_date: str) -> None:
    logger.info("─" * 50)
    logger.info("📅 Processando data: {}", target_date)

    tickets = _fetch_tickets_for_date(target_date)
    if not tickets:
        logger.info("Nenhum ticket para {}. Pulando.", target_date)
        return

    payload = aggregate_by_agent(tickets, target_date)
    _load_snapshot(payload)
    logger.info("✅ Snapshot de {} finalizado.", target_date)


# ---------------------------------------------------------------------------
# Range de datas para backfill
# ---------------------------------------------------------------------------

def _date_range(start_date: str) -> list[str]:
    """
    Retorna todas as datas entre start_date e D-1 (inclusive).
    Nunca inclui o dia atual — dados ainda abertos.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if start > ontem:
        logger.warning(
            "Data inicial {} é posterior a D-1 ({}). Nada a processar.",
            start_date, ontem.strftime("%Y-%m-%d"),
        )
        return []

    dates = []
    current = start
    while current <= ontem:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def run(force_date: str | None = None) -> None:
    setup_logger()
    logger.info("=" * 60)
    logger.info("🚀 Job 2: Snapshot Diário de CS — iniciando")
    logger.info("=" * 60)

    if force_date:
        # Backfill: de force_date até D-1
        dates = _date_range(force_date)
        logger.info("Modo backfill: {} → D-1 ({} dias a processar)", force_date, len(dates))
        for date in dates:
            process_date(date)
    else:
        # Padrão cron: só D-1
        ontem = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        process_date(ontem)

    logger.info("=" * 60)
    logger.info("🏁 Job 2 concluído.")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        # Sem argumento  → processa D-1
        # Com argumento  → backfill de force_date até D-1
        # ex: py jobs/job_daily_metrics.py 2026-05-01
        force = sys.argv[1] if len(sys.argv) > 1 else None
        run(force_date=force)
    except Exception as exc:
        logger.exception("💥 Job 2 encerrado com erro fatal: {}", exc)
        sys.exit(1)