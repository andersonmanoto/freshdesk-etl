"""
Etapa E (Extract) — parte 1:
  - Sincroniza agentes do Freshdesk → cs_agents
  - Carrega dicionários de lookup (agents, reasons, steps) em memória
"""

from loguru import logger

from services.freshdesk import fetch_agents, fetch_ticket_fields
from config.field_mappings import FIELD_TO_LOOKUP_TABLE
from services.supabase_client import get_supabase

# Tipo de retorno para os três dicionários de lookup
LookupDicts = tuple[dict[int, str], dict[str, str], dict[str, str]]


def _resolve_team(email: str) -> str:
    return "tiger" if "@tigeroffers.com" in email.lower() else "helpgrid"


def sync_agents() -> None:
    """Faz upsert dos agentes Freshdesk na tabela cs_agents."""
    logger.info("[Extract] Sincronizando agentes...")
    supabase = get_supabase()
    raw_agents = fetch_agents()

    payload = []
    for ag in raw_agents:
        contact = ag.get("contact", {})
        email = contact.get("email") or ""
        payload.append({
            "freshdesk_agent_id": ag["id"],
            "name": contact.get("name"),
            "email": email or None,
            "active": contact.get("active", True),
            "team": _resolve_team(email),
        })

    if payload:
        supabase.table("cs_agents").upsert(
            payload,
            on_conflict="freshdesk_agent_id",
        ).execute()
        logger.info("[Extract] {} agentes sincronizados.", len(payload))
    else:
        logger.warning("[Extract] Nenhum agente retornado pelo Freshdesk.")


def load_lookup_dicts() -> LookupDicts:
    """
    Carrega em memória os IDs das tabelas auxiliares para mapeamento O(1).

    Retorna:
        dict_agents  : freshdesk_agent_id → uuid interno
        dict_reasons : reason.lower()     → uuid interno
        dict_steps   : step_name.lower()  → uuid interno
    """
    logger.info("[Extract] Carregando lookups na memória...")
    supabase = get_supabase()

    res_agents = supabase.table("cs_agents").select("id, freshdesk_agent_id").execute()
    dict_agents: dict[int, str] = {
        row["freshdesk_agent_id"]: row["id"] for row in res_agents.data
    }

    res_reasons = supabase.table("cs_cancellation_reasons").select("id, reason").execute()
    dict_reasons: dict[str, str] = {
        row["reason"].lower(): row["id"] for row in res_reasons.data
    }

    res_steps = supabase.table("cs_retention_steps").select("id, step_name").execute()
    dict_steps: dict[str, str] = {
        row["step_name"].lower(): row["id"] for row in res_steps.data
    }

    logger.debug(
        "[Extract] Lookups carregados — agents: {}, reasons: {}, steps: {}",
        len(dict_agents), len(dict_reasons), len(dict_steps),
    )
    return dict_agents, dict_reasons, dict_steps

def sync_lookup_fields() -> None:
    """
    Busca os choices dos custom fields relevantes e faz upsert
    nas tabelas de lookup correspondentes.
    """
    logger.info("[Extract] Sincronizando lookup fields...")
    supabase = get_supabase()
    fields = fetch_ticket_fields()

    field_map = {f["name"]: f for f in fields if f["name"] in FIELD_TO_LOOKUP_TABLE}

    for field_name, (table, column) in FIELD_TO_LOOKUP_TABLE.items():
        field = field_map.get(field_name)
        if not field:
            logger.warning("[Extract] Field '{}' não encontrado no Freshdesk.", field_name)
            continue

        choices = field.get("choices", [])
        if not choices:
            logger.warning("[Extract] Field '{}' sem choices.", field_name)
            continue

        payload = [{column: choice} for choice in choices]
        supabase.table(table).upsert(payload, on_conflict=column).execute()
        logger.info("[Extract] {} — {} choices sincronizados em '{}'.", field_name, len(payload), table)