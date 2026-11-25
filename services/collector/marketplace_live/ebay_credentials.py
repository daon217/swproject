"""Explicit eBay dotenv loading; transactional, no logging or file writes."""
import os
from pathlib import Path


def load_ebay_env(path):
    file = Path(path)
    names = ('EBAY_CLIENT_ID', 'EBAY_CLIENT_SECRET')
    if not file.is_file() or file.stat().st_size > 65536:
        raise ValueError('ebay_env_file_unavailable')
    values = {name: [] for name in names}
    for line in file.read_text(encoding='utf-8-sig').splitlines():
        name, separator, value = line.strip().removeprefix('export ').partition('=')
        if not separator or name.strip() not in values:
            continue
        value = value.strip()
        if value[:1] in ('"', "'"):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('ebay_env_value_invalid')
            value = value[1:-1]
        else:
            value = value.split(' #', 1)[0].strip()
        values[name.strip()].append(value)
    loaded = {}
    for name, candidates in values.items():
        if len(candidates) != 1 or not candidates[0] or any(not 33 <= ord(c) <= 126 for c in candidates[0]):
            raise ValueError('ebay_env_key_missing_or_ambiguous')
        if os.environ.get(name) and os.environ[name] != candidates[0]:
            raise ValueError('ebay_env_conflicts_with_process')
        loaded[name] = candidates[0]
    os.environ.update(loaded)
