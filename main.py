"""
Ponto de entrada do ETL Freshdesk → Supabase.

Fluxo:
  1. Lê last_run do Supabase (etl_state)
py   2. Sincroniza agentes, lookup fields e carrega dicts na memória
  3. Extrai tickets atualizados desde last_run
  4. Cruza tickets com dados de vendas
  5. Transforma payload
  6. Carrega no Supabase (upsert chunked)
  7. Persiste novo last_run
"""

import sys

from loguru import logger

from utils.logger import setup_logger
from services.freshdesk import fetch_tickets_since
from steps.extract import sync_agents, sync_lookup_fields, load_lookup_dicts
from steps.enrich import build_sales_index
from steps.transform import transform_tickets
from steps.load import get_last_run, load_tickets, save_last_run


def run() -> None:
    setup_logger()
    logger.info("=" * 60)
    logger.info("🚀 ETL Freshdesk → Supabase — iniciando")
    logger.info("=" * 60)

    # 1. Estado
    last_run = get_last_run()
    logger.info("Janela de extração: desde {}", last_run)

    # 2. Agentes + lookups (Fields)
    sync_agents()
    sync_lookup_fields()
    lookup_dicts = load_lookup_dicts()

    # 3. Extração
    raw_tickets = fetch_tickets_since(last_run)
    if not raw_tickets:
        logger.info("✅ Nenhum ticket novo ou atualizado. Encerrando.")
        return

    # 4. Enriquecimento
    sales_index = build_sales_index(raw_tickets)

    # 5. Transformação
    payload, latest_updated = transform_tickets(raw_tickets, lookup_dicts, sales_index)

    # 6. Carga
    load_tickets(payload)

    # 7. Atualiza estado — só após carga bem-sucedida
    save_last_run(latest_updated)

    logger.info("=" * 60)
    logger.info("🏁 ETL concluído. Próxima execução desde: {}", latest_updated)
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("💥 ETL encerrado com erro fatal: {}", exc)
        sys.exit(1)
