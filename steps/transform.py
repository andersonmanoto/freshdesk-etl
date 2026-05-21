"""
Etapa T (Transform):
  - Normaliza cada ticket bruto
  - Resolve lookups (agent, reason, step)
  - Calcula campos derivados (interval_days, has_upsell, retained_value)
  - Retorna o payload pronto para o upsert + o maior updated_at visto
"""

from dateutil import parser as dtparser
from loguru import logger

from steps.enrich import SalesIndex
from steps.extract import LookupDicts


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _resolve_agent(t: dict, dict_agents: dict) -> str | None:
    responder_id = t.get("responder_id")
    return dict_agents.get(responder_id) if responder_id else None


def _resolve_reason(cf: dict, dict_reasons: dict) -> tuple[str | None, str | None]:
    """Retorna (reason_id, reason_raw)."""
    motivo = cf.get("cf_motivo_da_solicitao")
    reason_id = dict_reasons.get(motivo.lower()) if motivo else None
    return reason_id, motivo


def _resolve_step(cf: dict, dict_steps: dict) -> str | None:
    degrau = cf.get("cf_degrau_aplicado")
    return dict_steps.get(degrau.lower()) if degrau else None


def _calc_interval_days(ticket: dict, venda: dict) -> int | None:
    """Dias entre a data da venda e a criação do ticket. None em caso de erro."""
    if not venda.get("event_date"):
        return None
    try:
        data_venda = dtparser.parse(venda["event_date"]).replace(tzinfo=None)
        data_ticket = dtparser.parse(ticket["created_at"]).replace(tzinfo=None)
        return (data_ticket - data_venda).days
    except Exception as exc:
        logger.warning(
            "[Transform] Erro ao calcular interval_days para ticket {}: {}",
            ticket.get("id"),
            exc,
        )
        return None


def _parse_upsell(cf: dict) -> bool | None:
    raw = cf.get("cf_tem_upsell")
    if raw is None:
        return None
    return raw == "Sim"


def _build_row(
    ticket: dict,
    venda: dict,
    dict_agents: dict,
    dict_reasons: dict,
    dict_steps: dict,
) -> dict:
    cf = ticket.get("custom_fields", {})
    order_id = cf.get("cf_bg_order_id")

    reason_id, reason_raw = _resolve_reason(cf, dict_reasons)
    resultado = cf.get("cf_resultado")

    return {
        "freshdesk_ticket_id": ticket["id"],
        "fd_created_at": ticket["created_at"],
        "fd_updated_at": ticket["updated_at"],
        "fd_resolved_at": ticket.get("stats", {}).get("resolved_at"),
        "status": ticket["status"],
        "priority": ticket["priority"],
        "ticket_type": ticket.get("type"),
        "subject": ticket.get("subject"),
        "contact_email": ticket.get("requester", {}).get("email"),
        "contact_name": ticket.get("requester", {}).get("name"),
        # Dados de venda
        "order_id": order_id,
        "event_id": venda.get("id"),
        "product_id": venda.get("product_id"),
        "affiliate_id": venda.get("affiliate_id"),
        "network_id": venda.get("network_id"),
        "interval_days": _calc_interval_days(ticket, venda),
        # Lookups resolvidos
        "agent_id": _resolve_agent(ticket, dict_agents),
        "reason_id": reason_id,
        "reason_raw": reason_raw,
        "retention_step_id": _resolve_step(cf, dict_steps),
        # Campos analíticos
        "retention_outcome": resultado,
        "retained_value": cf.get("cf_valor_total") if resultado == "Retido" else 0,
        "has_upsell": _parse_upsell(cf),
        "client_tier": cf.get("cf_tier_do_cliente"),
        "platform": cf.get("cf_plataforma"),
        "payment_method": cf.get("cf_forma_de_pagamento"),
    }


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def transform_tickets(
    raw_tickets: list[dict],
    lookup_dicts: LookupDicts,
    sales_index: SalesIndex,
) -> tuple[list[dict], str]:
    """
    Transforma a lista bruta de tickets em payload Supabase.

    Retorna:
        payload        : lista de dicts prontos para upsert
        latest_updated : maior fd_updated_at visto (para atualizar o estado)
    """
    logger.info("[Transform] Transformando {} tickets...", len(raw_tickets))
    dict_agents, dict_reasons, dict_steps = lookup_dicts

    payload: list[dict] = []
    latest_updated = ""
    errors = 0

    for ticket in raw_tickets:
        try:
            venda = sales_index.get(
                ticket.get("custom_fields", {}).get("cf_bg_order_id"), {}
            )
            row = _build_row(ticket, venda, dict_agents, dict_reasons, dict_steps)
            payload.append(row)

            if ticket["updated_at"] > latest_updated:
                latest_updated = ticket["updated_at"]

        except Exception as exc:
            errors += 1
            logger.error(
                "[Transform] Falha ao processar ticket {} — ignorado. Erro: {}",
                ticket.get("id"),
                exc,
            )

    logger.info(
        "[Transform] Concluído — {} rows gerados, {} erros.",
        len(payload),
        errors,
    )
    return payload, latest_updated
