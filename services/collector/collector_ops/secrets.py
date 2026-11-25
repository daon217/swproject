"""Read explicitly named Docker secrets; never discover dotenv files or log values."""
import os
from pathlib import Path

KEYS={'domeggook':['DOMEGGOOK_API_KEY'],'yes24':['YES24_API_KEY'],
      'serper':['SERPER_API_KEY'],'ebay':['EBAY_CLIENT_ID','EBAY_CLIENT_SECRET'],
      'ebay_used':['EBAY_CLIENT_ID','EBAY_CLIENT_SECRET']}


def load(provider, backend=False):
    names=KEYS[provider]+(['KKULPICK_BACKEND_TOKEN'] if backend else [])
    values={}
    for name in names:
        path=os.environ.get(name+'_FILE')
        value=os.environ.get(name,'')
        if path:
            file=Path(path)
            if not file.is_file() or file.stat().st_size>16384:raise ValueError('secret_file_invalid')
            stored=file.read_text(encoding='utf-8-sig').strip()
            if value and value!=stored:raise ValueError('secret_environment_conflict')
            value=stored
        if not value or any(not 33<=ord(c)<=126 for c in value):raise ValueError('secret_missing_or_invalid')
        if name=='KKULPICK_BACKEND_TOKEN' and len(value)<32:raise ValueError('backend_token_minimum_length_required')
        values[name]=value
    os.environ.update(values)
    return {name:True for name in names}
