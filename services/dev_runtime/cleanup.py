"""Delete expired blobs only from the dedicated private development image directory."""
import os
from pathlib import Path
import time

root = Path('/var/lib/kkulpick/images')
ttl = max(60, int(os.getenv('TEMP_IMAGE_TTL_SECONDS', '3600')))
while True:
    cutoff = time.time() - ttl
    for path in root.glob('*.bin'):
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                path.unlink()
        except FileNotFoundError:
            pass
    time.sleep(60)
