"""Existing HTTPS/token transport with an optional trusted NAS CA file."""
import os
from pathlib import Path
from services.collector.marketplace_live.delivery import Outbox,RetryAwareBackend


def configure_CA(transport):
    if getattr(transport,'internal_http',False) is True:return transport  # HTTP has no CA/deployment file dependency.
    path=os.environ.get('COLLECTOR_CA_FILE')
    if path:
        if not Path(path).is_file():raise ValueError('trusted_CA_file_required')
        transport.session.verify=path
    # Certificate verification is never disabled.
    return transport


class OpsOutbox(Outbox):
    def flush(self,stop=None):
        before=self.state['totals'].get('revoked',0)
        self.prune()
        if self.enabled and self.state['totals'].get('revoked',0)!=before:self.save()
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return self.report()
        if self.transport is None and self.ready and self.enabled and self.pending_count():
            from .backend_transport import build_backend
            self.transport=configure_CA(build_backend(self.settings.get('base_url',''),os.environ.get('KKULPICK_BACKEND_TOKEN',''),self.clock))
        return super().flush(stop)
