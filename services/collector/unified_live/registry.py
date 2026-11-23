"""Explicit domain registration; never silently overwrite a registered configuration."""
from pathlib import Path
from urllib.parse import urlsplit
from services.collector.domeggook_live.domeggook_delivery import atomic,load
from services.collector.domeggook_live.runtime import FileState
from .policy import validate

def register(cfg,root):
    validate(cfg);path=Path(root)/'registry.json'
    with FileState(Path(root)/'registry-lock').lock():
        data=load(path,{'version':1,'domains':{}})
        if data.get('version')!=1:raise ValueError('registry_version_no_reset')
        host=urlsplit(cfg['base_url']).hostname
        old=data['domains'].get(host)
        if old and old!=cfg:raise ValueError('registered_domain_changed_requires_review')
        if any(v['source']==cfg['source'] and k!=host for k,v in data['domains'].items()):raise ValueError('source_already_registered')
        data['domains'][host]=cfg;atomic(path,data)
    return {'source':cfg['source'],'registered':True,'enabled':cfg['enabled'],'HTTP_requests':0}
