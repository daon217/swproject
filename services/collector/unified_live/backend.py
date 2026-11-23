"""Separate collection/queue permission from actual team API send approval."""
import os
from services.collector.collector_ops.backend import OpsOutbox
from pathlib import Path

def load_backend_token():
    name='KKULPICK_BACKEND_TOKEN';value=os.environ.get(name,'');path=os.environ.get(name+'_FILE')
    if path:
        p=Path(path)
        if not p.is_file() or p.stat().st_size>16384:raise ValueError('backend_secret_file_invalid')
        stored=p.read_text(encoding='utf-8-sig').strip()
        if value and value!=stored:raise ValueError('backend_secret_conflict')
        value=stored
    if len(value)<32 or any(not 33<=ord(c)<=126 for c in value):raise ValueError('backend_secret_invalid')
    os.environ[name]=value
    return True

class ApprovedOutbox(OpsOutbox):
    def flush(self,stop=None):
        before=self.state['totals'].get('revoked',0)
        self.prune()
        if self.state['totals'].get('revoked',0)!=before:self.save()
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return self.report()
        if len(os.environ.get('KKULPICK_BACKEND_TOKEN',''))<32:return self.report()
        return super().flush(stop=stop)
