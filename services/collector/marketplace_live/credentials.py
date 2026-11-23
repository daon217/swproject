"""Explicit, single-variable dotenv import. No discovery, logging or file writes."""
import os
from pathlib import Path

def load_serper_env(path):
    file=Path(path)
    if not file.is_file() or file.stat().st_size>65536:raise ValueError('serper_env_file_unavailable')
    values=[]
    for line in file.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        name,sep,value=line.removeprefix('export ').partition('=')
        if not sep or name.strip()!='SERPER_API_KEY':continue
        value=value.strip()
        if value[:1] in ('\"',"'"):
            if len(value)<2 or value[-1]!=value[0]:raise ValueError('serper_env_value_invalid')
            value=value[1:-1]
        else:value=value.split(' #',1)[0].strip()
        values.append(value)
    if len(values)!=1 or not values[0] or any(not 33<=ord(c)<=126 for c in values[0]):
        raise ValueError('serper_env_key_missing_or_ambiguous')
    existing=os.environ.get('SERPER_API_KEY')
    if existing and existing!=values[0]:raise ValueError('serper_env_conflicts_with_process')
    os.environ['SERPER_API_KEY']=values[0]
