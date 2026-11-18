"""Portable runtime primitives, extracted from the existing collector helpers."""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import copy,json,os,re

PACKAGE=Path(__file__).resolve().parent
STATE_ROOT=Path(os.environ.get('KKULPICK_STATE_DIR') or PACKAGE/'data').resolve()
FIELDS='product_name price currency seller product_url image_url category brand description specifications rating rating_scale review_count condition shipping_fee'.split()

def read(path,default=None):
    path=Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else copy.deepcopy(default)

def now():return datetime.now(timezone.utc).isoformat()

def public_url(value):
    if not isinstance(value,str) or any(ord(c)<32 for c in value):return False
    try:
        parsed=urlsplit(value)
        return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:return False

def identity(source,value):
    if source!='domeggook' or not isinstance(value,str):return None
    parsed=urlsplit(value)
    if parsed.hostname not in ('domeggook.com','www.domeggook.com'):return None
    ident=parsed.path.strip('/')
    if ident.isdigit():return ident
    values=parse_qs(parsed.query).get('no',[])
    return values[0] if len(values)==1 and values[0].isdigit() else None

class FileState:
    def __init__(self,directory):self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
    @contextmanager
    def lock(self):
        fd=os.open(self.directory/'writer.lock',os.O_CREAT|os.O_RDWR)
        try:
            if os.fstat(fd).st_size==0:os.write(fd,b'0')
            os.lseek(fd,0,os.SEEK_SET)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:yield
            finally:
                os.lseek(fd,0,os.SEEK_SET)
                if os.name=='nt':msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
                else:fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)
