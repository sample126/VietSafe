"""Configuration and local environment loader. Never embed tokens in code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'frontend'
DB_PATH = ROOT / 'data' / 'vietsafe.sqlite3'
MAX_BODY = 2_200_000

def load_local_env(path=None):
    """Load supported environment variables without overriding higher-priority values."""
    env_path = Path(path) if path is not None else ROOT / '.env'
    try:
        lines = env_path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return
    for line_number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, separator, value = line.partition('=')
        name = name.strip()
        if not separator or name not in ('TOMTOM_API_KEY', 'NASA_EARTHDATA_TOKEN', 'VIETSAFE_ADMIN_PASSWORD'):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if '\n' in value or '\r' in value:
            raise ValueError(f'Giá trị trong {env_path.name}, dòng {line_number}, không hợp lệ.')
        os.environ.setdefault(name, value)

# Process environment takes precedence over private local files.
load_local_env(ROOT / '.env.local')
load_local_env(ROOT / '.env')
