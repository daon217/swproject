import os
import secrets
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from uuid import UUID


class Probe(BaseModel):
    model_config = ConfigDict(extra='forbid')
    correlation_id: UUID


def make_app(role: str) -> FastAPI:
    app = FastAPI(title=f'꿀픽 {role} 개발 연결', version='0.1.0')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': role, 'implementation': 'development-scaffold',
                'business_ready': False}

    @app.post('/internal/dev/probe')
    def probe(body: Probe, authorization: str = Header(default='')):
        token = os.environ.get('WORKSPACE_TOKEN', '')
        if len(token) < 32 or not secrets.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
            raise HTTPException(401, 'SERVICE_AUTH_REQUIRED')
        return {'correlation_id': str(body.correlation_id), 'service': role,
                'implementation': 'development-scaffold', 'business_ready': False}

    @app.post('/internal/process')
    def process():
        raise HTTPException(501, 'BUSINESS_ADAPTER_NOT_IMPLEMENTED')

    return app
