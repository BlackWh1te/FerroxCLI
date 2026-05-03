import logging
from pathlib import Path


def setup_logger():
    log_dir = Path.home() / ".ferrox"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "debug.log"

    logging.basicConfig(
        filename=log_file, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    return logging.getLogger("ferrox")


logger = setup_logger()
