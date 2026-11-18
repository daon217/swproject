"""Private bounded upload storage. Images are not publicly served or decoded here."""
import logging
import os
from pathlib import Path
import time
from uuid import UUID,uuid4
from .members import fail

MAX_IMAGE=2*1024*1024


def directory():
    root=Path(os.getenv('ANALYSIS_IMAGE_DIR','/tmp/kkulpick-analysis-images'))
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    return root


def image_path(ident):
    return directory()/(str(UUID(str(ident)))+'.bin')


def save_image(data):
    if not data or len(data)>MAX_IMAGE:fail(413,'IMAGE_TOO_LARGE')
    valid=(data.startswith(b'\x89PNG\r\n\x1a\n') or
           (data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')) or
           (data.startswith(b'RIFF') and data[8:12]==b'WEBP'))
    if not valid:fail(415,'IMAGE_FORMAT_UNSUPPORTED')
    ident=uuid4()
    fd=os.open(image_path(ident),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as out:out.write(data)
    return ident


def remove_image(ident):
    if ident is None:return
    image_path(ident).unlink(missing_ok=True)


def sweep_images(max_age=3600,batch=500):
    deleted=0
    for path in directory().glob('*.bin'):
        try:
            UUID(path.stem)
            if path.stat().st_mtime<time.time()-max_age:
                path.unlink(missing_ok=True);deleted+=1
            if deleted>=batch:break
        except FileNotFoundError:pass
        except (ValueError,OSError):
            logging.getLogger('kkulpick').warning('image_cleanup_failed')
    return deleted
