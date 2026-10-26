"""Конфигурация из локального .env; значения секретов не журналируются."""
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str
    token: str
    model: str
    base_url: str
    mcp_url: str
    allowed_ids: frozenset[int]


def settings():
    load_dotenv(ROOT / '.env')
    key = os.getenv('OPENAI_API_KEY', '').strip()
    token = os.getenv('BOT_TOKEN', '').strip()
    if not key or not token:
        raise ValueError('Заполните OPENAI_API_KEY и BOT_TOKEN в .env')
    ids = frozenset(int(x.strip()) for x in os.getenv('ALLOWED_USER_IDS', '').split(',') if x.strip())
    return Settings(key, token, os.getenv('CHAT_MODEL') or 'gpt-6-luna',
                    os.getenv('OPENAI_BASE_URL') or 'https://api.openai.com/v1',
                    os.getenv('MCP_URL') or 'http://127.0.0.1:8008/mcp', ids)


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    for name in ('httpx', 'httpcore', 'httpx2', 'httpcore2', 'openai', 'aiogram.event'):
        logging.getLogger(name).setLevel(logging.CRITICAL)


@contextmanager
def instance_lock(token):
    import fcntl
    import hashlib
    # Общая блокировка для копий VPf08 с одним токеном; ключ в имени не раскрывается.
    import tempfile
    path = Path(tempfile.gettempdir()) / ('vpf08-' + hashlib.sha256(token.encode()).hexdigest()[:16] + '.lock')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('VPf08 с этим токеном уже запущен') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
