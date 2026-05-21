"""
Etapa E (Extract) — parte 2:
  - Coleta os order_ids presentes nos tickets
  - Cruza com a tabela de eventos/vendas no Supabase
"""

from loguru import logger

from services.supabase_client import get_supabase

# order_id → registro de venda
SalesIndex = dict[str, dict]


def build_sales_index(tickets: list[dict]) -> SalesIndex:
    """
    Recebe a lista bruta de tickets e retorna um índice { order_id: evento }
    consultando a tabela `events` no Supabase.
    """
    order_ids = {
        t.get("custom_fields", {}).get("cf_bg_order_id")
        for t in tickets
        if t.get("custom_fields", {}).get("cf_bg_order_id")
    }

    if not order_ids:
        logger.warning(
            "[Enrich] Nenhum order_id encontrado nos tickets — índice de vendas vazio."
        )
        return {}

    logger.info(
        "[Enrich] Cruzando {} order_ids com a tabela de eventos...", len(order_ids)
    )

    supabase = get_supabase()
    ids_list = list(order_ids)
    chunk_size = 500  # seguro para não estourar o limite de URL do PostgREST
    all_rows: list[dict] = []

    for i in range(0, len(ids_list), chunk_size):
        chunk = ids_list[i : i + chunk_size]
        res = (
            supabase.table("events")
            .select("id, order_id, product_id, affiliate_id, network_id, event_date")
            .in_("order_id", chunk)
            .execute()
        )
        all_rows.extend(res.data)
        logger.debug(
            "[Enrich] Chunk {}/{} — {} rows retornados.",
            i // chunk_size + 1,
            -(-len(ids_list) // chunk_size),
            len(res.data),
        )

    index: SalesIndex = {ev["order_id"]: ev for ev in all_rows}
    logger.info("[Enrich] {} order_ids encontrados na tabela de eventos.", len(index))

    missing = order_ids - index.keys()
    if missing:
        logger.debug(
            "[Enrich] {} order_ids sem correspondência em events.", len(missing)
        )

    return index
