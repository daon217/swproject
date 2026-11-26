"""#64 회귀: OCR 예외에도 세션이 '처리 중'에 멈추지 않고, 늦은 실패 마감이 성공을 덮지 않는다."""
import json

import fakeredis
import numpy as np
import pytest

from app import tasks


@pytest.fixture
def r(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(tasks, 'get_redis_client', lambda: fake)
    monkeypatch.setattr(tasks, 'decode_image', lambda _: np.zeros((10, 10, 3), dtype=np.uint8))
    return fake


def test_ocr_exception_on_last_frame_finishes_the_session(r, monkeypatch):
    tasks.initialize_session_in_redis('s1', 'SYNTHETIC', None)
    monkeypatch.setattr(tasks, '_scan_frame', lambda holder: (_ for _ in ()).throw(RuntimeError('ocr crashed')))
    out = tasks.process_frame_task.run('s1', 0, True, 'aW1n')
    assert out['status'] == 'analysis_unavailable'
    assert r.hget(tasks.get_session_key('s1'), 'status') == 'analysis_unavailable'


def test_late_failure_does_not_overwrite_success(r):
    tasks.initialize_session_in_redis('s2', 'SYNTHETIC', None)
    tasks.finalize_session_state(r, 's2', 'success', ['밀'], 'ok')
    tasks.finalize_session_state(r, 's2', 'analysis_unavailable', [], 'late')
    key = tasks.get_session_key('s2')
    assert r.hget(key, 'status') == 'success' and json.loads(r.hget(key, 'ingredients')) == ['밀']
