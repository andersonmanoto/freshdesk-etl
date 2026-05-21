import sys
from loguru import logger


def setup_logger() -> None:
    """
    Configura o Loguru com dois sinks:
      - stdout: nível INFO, formato legível para humanos
      - arquivo rotativo: nível DEBUG, retido por 7 dias
    """
    logger.remove()  # remove o handler padrão

    logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    logger.add(
        "logs/etl_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",       # novo arquivo à meia-noite
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )
