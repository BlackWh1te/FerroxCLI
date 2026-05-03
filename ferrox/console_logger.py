import logging

from rich.console import Console

from .logger_new import logger

console = Console()


def handle_log_record(record):
    if record.levelname == "WARNING":
        console.print(f"[yellow]⚠️[/yellow] {record.getMessage()}")
    elif record.levelname == "ERROR":
        console.print(f"[red]❌[/red] {record.getMessage()}")
    elif record.levelname == "INFO" and "Fallback triggered" in record.getMessage():
        console.print(f"[cyan]🔄[/cyan] {record.getMessage()}")


class UIHandler(logging.Handler):
    def emit(self, record):
        handle_log_record(record)


# Initialize and hook into the main logger
logger.addHandler(UIHandler())
