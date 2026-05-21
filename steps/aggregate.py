"""
Etapa de Agregação (Snapshot Diário):
  - Recebe lista de tickets de um dia específico
  - Agrupa por agent_id em memória
  - Calcula métricas de performance por agente
  - Retorna payload pronto para upsert em snapshot_daily_cs_agent

Nota: retention_rate é uma GENERATED COLUMN no Postgres —
não é calculada aqui nem incluída no payload.
"""

from loguru import logger

# Tipo do payload final
AgentSnapshot = dict[str, object]


def _init_agent(agent_id: str, snapshot_date: str) -> AgentSnapshot:
    return {
        "agent_id":            agent_id,
        "snapshot_date":       snapshot_date,
        "total_tickets":       0,
        "tickets_resolved":    0,
        "retention_attempts":  0,
        "retentions_saved":    0,
        "retained_value":      0.0,
        "refunds_issued":      0,
        "total_refund_amount": 0.0,
        "chargebacks_handled": 0,
    }


def _process_ticket(data: AgentSnapshot, ticket: dict) -> None:
    data["total_tickets"] += 1

    # Status 4 = Resolved, 5 = Closed
    if ticket.get("status") in [4, 5]:
        data["tickets_resolved"] += 1

    # Chargeback vem do ticket_type, não do retention_outcome
    if ticket.get("ticket_type") == "Chargeback":
        data["chargebacks_handled"] += 1

    outcome = (ticket.get("retention_outcome") or "").strip().lower()

    # Tentativa de retenção = tem degrau preenchido OU tem resultado
    if ticket.get("retention_step_id") or outcome:
        data["retention_attempts"] += 1

    if outcome == "retido":
        data["retentions_saved"] += 1
        data["retained_value"] += float(ticket.get("retained_value") or 0)

    elif outcome == "parcial":
        # Parcial conta como tentativa (já somado acima) mas não como salvo nem reembolsado
        # retained_value parcial também é registrado se preenchido
        data["retained_value"] += float(ticket.get("retained_value") or 0)

    elif outcome == "reembolsado":
        data["refunds_issued"] += 1
        data["total_refund_amount"] += float(ticket.get("retained_value") or 0)


def aggregate_by_agent(tickets: list[dict], snapshot_date: str) -> list[AgentSnapshot]:
    """
    Recebe tickets de um único dia e retorna uma lista de snapshots por agente,
    prontos para upsert em snapshot_daily_cs_agent.
    retention_rate é omitida — calculada automaticamente pelo Postgres (GENERATED ALWAYS).
    """
    logger.info("[Aggregate] Processando {} tickets para {}...", len(tickets), snapshot_date)

    agents_data: dict[str, AgentSnapshot] = {}
    skipped = 0

    for ticket in tickets:
        agent_id = ticket.get("agent_id")
        if not agent_id:
            skipped += 1
            continue

        if agent_id not in agents_data:
            agents_data[agent_id] = _init_agent(agent_id, snapshot_date)

        _process_ticket(agents_data[agent_id], ticket)

    payload = list(agents_data.values())

    logger.info(
        "[Aggregate] {} snapshots gerados, {} tickets sem agente ignorados.",
        len(payload), skipped,
    )
    return payload