from typing import Any

import requests
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import settings

# Erros que justificam retry (rede, rate-limit, 5xx)
_RETRYABLE = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
)

_SESSION = requests.Session()


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return status in {429, 500, 502, 503, 504}
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, "WARNING"),
    reraise=True,
)
def _get(url: str, params: dict | None = None) -> Any:
    response = _SESSION.get(
        url,
        auth=settings.fd_auth,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Agentes
# ---------------------------------------------------------------------------

def fetch_agents() -> list[dict]:
    """Retorna todos os agentes cadastrados no Freshdesk."""
    logger.debug("Buscando agentes no Freshdesk...")
    agents = _get(f"{settings.fd_base_url}/agents")
    logger.debug("Agentes encontrados: {}", len(agents))
    return agents


# ---------------------------------------------------------------------------
# Tickets paginados
# ---------------------------------------------------------------------------

def fetch_tickets_since(updated_since: str) -> list[dict]:
    """
    Retorna todos os tickets atualizados após `updated_since` (ISO 8601).
    Respeita o limite de 300 páginas da API e loga um aviso se atingido.
    """
    logger.info("Buscando tickets atualizados desde {}", updated_since)
    all_tickets: list[dict] = []

    for page in range(1, settings.freshdesk_max_pages + 1):
        params = {
            "updated_since": updated_since,
            "include": "requester,stats",
            "page": page,
            "per_page": settings.freshdesk_per_page,
        }
        batch = _get(f"{settings.fd_base_url}/tickets", params=params)

        if not batch:
            logger.debug("Paginação encerrada na página {}", page)
            break

        all_tickets.extend(batch)
        logger.debug("Página {} → {} tickets (total acumulado: {})", page, len(batch), len(all_tickets))

        if len(batch) < settings.freshdesk_per_page:
            break  # última página parcial — não vale fazer mais um request
    else:
        logger.warning(
            "Limite de {} páginas atingido — podem existir tickets não coletados. "
            "Considere reduzir o intervalo de sincronização.",
            settings.freshdesk_max_pages,
        )

    logger.info("Total de tickets extraídos: {}", len(all_tickets))
    return all_tickets

# ---------------------------------------------------------------------------
# Ticket Fields
# ---------------------------------------------------------------------------

def fetch_ticket_fields() -> list[dict]:
    """Retorna todos os campos de ticket do Freshdesk."""
    logger.debug("Buscando ticket fields no Freshdesk...")
    fields = _get(f"{settings.fd_base_url}/ticket_fields")
    logger.debug("Fields encontrados: {}", len(fields))
    return fields