import logging
import pathlib
import signal
import threading
import time

from src.app import create_app

logger = logging.getLogger("scheduler_runner")

HEARTBEAT_FILE = pathlib.Path("/tmp/scheduler_heartbeat")
HEARTBEAT_INTERVAL = 30


def _heartbeat_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        HEARTBEAT_FILE.touch()
        stop_event.wait(HEARTBEAT_INTERVAL)


def main() -> None:
    app = create_app()
    if not app.config.get("SCHEDULER_ENABLED"):
        logger.error("SCHEDULER_ENABLED is false; refusing to start scheduler runner")
        return

    stop_event = threading.Event()

    heartbeat = threading.Thread(target=_heartbeat_loop, args=(stop_event,), daemon=True)
    heartbeat.start()

    def handle_signal(signum, _frame):
        logger.info("Received signal %d, shutting down scheduler runner", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Scheduler runner started, waiting for shutdown signal")
    stop_event.wait()
    logger.info("Scheduler runner exiting")


if __name__ == "__main__":
    main()
