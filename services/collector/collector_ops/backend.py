"""Existing HTTPS/token transport with an optional trusted NAS CA file."""
import os
from pathlib import Path
from services.collector.marketplace_live.delivery import Outbox,RetryAwareBackend


def configure_CA(transport):
    path=os.environ.get('COLLECTOR_CA_FILE')
    if path:
        if not Path(path).is_file():raise ValueError('trusted_CA_file_required')
        transport.session.verify=path
    # Certificate verification is never disabled.
    return transport


class OpsOutbox(Outbox):
    def flush(self,stop=None):
        if self.transport is None and self.ready and self.enabled and self.pending_count():
            self.transport=configure_CA(RetryAwareBackend(self.settings.get('base_url',''),os.environ.get('KKULPICK_BACKEND_TOKEN',''),self.clock))
        return super().flush(stop)
