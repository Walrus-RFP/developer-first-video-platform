"""
Structured JSON logging for the video platform.
Usage:
    from utils.logger import logger
    logger.info("Something happened", extra={"video_id": "abc123"})
"""
import logging
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Outputs each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        # Merge any extra keys the caller passed
        for key in ("video_id", "session_id", "blob_id", "user_address",
                     "event", "url", "status_code", "error", "detail"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info and record.exc_info[0]:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _build_logger(name: str = "walrus") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        # Console handler
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(JSONFormatter())
        log.addHandler(stdout_handler)
        
        # File handler for remote debugging
        file_handler = logging.FileHandler("app.log", mode="a")
        file_handler.setFormatter(JSONFormatter())
        log.addHandler(file_handler)
        
        log.setLevel(logging.DEBUG)
        log.propagate = False
    return log


logger = _build_logger()
