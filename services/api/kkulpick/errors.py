"""Stable frontend errors, correlation IDs and credential-safe server diagnostics."""
import logging
from uuid import uuid4
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

MESSAGES = {
    'INVALID_CREDENTIALS': '아이디 또는 비밀번호를 확인해 주세요.',
    'AUTH_REQUIRED': '로그인이 필요합니다.',
    'LOGIN_ID_TAKEN': '이미 사용 중인 아이디입니다.',
    'VERSION_CONFLICT': '정보가 변경되었습니다. 새로고침 후 다시 저장해 주세요.',
    'PAYMENT_FAILED': '결제에 실패했습니다. 결제 내역을 확인해 주세요.',
    'PAYMENT_PENDING': '이전 결제 결과를 확인 중입니다. 중복 결제를 진행하지 마세요.',
    'SUBSCRIPTION_ALREADY_ACTIVE': '이미 이용 중인 구독이 있습니다.',
    'PAYMENT_PROVIDER_NOT_CONFIGURED': '결제 서비스가 아직 연결되지 않았습니다.',
    'WRONG_PASSWORD': '현재 비밀번호가 일치하지 않습니다.',
    'DATABASE_UNAVAILABLE': '일시적으로 저장소에 연결할 수 없습니다.',
    'INVALID_INPUT': '입력한 정보의 형식과 필수 항목을 확인해 주세요.',
    'AUTH_RATE_LIMITED': '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.',
}


def reply(req, status, code, headers=None, **extra):
    rid = getattr(req.state, 'request_id', uuid4().hex)
    return JSONResponse(status_code=status, headers={'X-Request-ID': rid, **(headers or {})}, content={
        'error': {'code': code, 'message': MESSAGES.get(code, '요청을 처리하지 못했습니다.'),
                  'retryable': status in {429, 503}},
        'detail': code, 'request_id': rid, **extra,
    })


def install_errors(app):
    @app.middleware('http')
    async def request_id(req, call_next):
        req.state.request_id = uuid4().hex
        response = await call_next(req)
        response.headers['X-Request-ID'] = req.state.request_id
        if req.url.path.startswith(('/v2/', '/internal/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(HTTPException)
    async def http_error(req, exc):
        code = exc.detail if isinstance(exc.detail, str) and exc.detail.isupper() else 'REQUEST_FAILED'
        return reply(req, exc.status_code, code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(req, exc):
        # Never return input values, password fields, SQL or provider secrets.
        return reply(req, 422, 'INVALID_INPUT', fields=[list(e['loc']) for e in exc.errors()])

    @app.exception_handler(IntegrityError)
    async def conflict(req, exc):
        return reply(req, 409, 'DATA_CONFLICT')

    @app.exception_handler(SQLAlchemyError)
    async def database_error(req, exc):
        logging.getLogger('kkulpick').error('database_error request_id=%s type=%s', req.state.request_id, type(exc).__name__)
        return reply(req, 503, 'DATABASE_UNAVAILABLE', headers={'Retry-After': '3'})

    @app.exception_handler(Exception)
    async def unexpected(req, exc):
        logging.getLogger('kkulpick').error('unhandled_error request_id=%s type=%s', getattr(req.state, 'request_id', '-'), type(exc).__name__)
        return reply(req, 500, 'INTERNAL_ERROR')
