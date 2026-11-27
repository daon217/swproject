"""Phase 1 전 쇼핑몰 레이아웃 상품명 추출, 서랍장·운동화 등 다중 신호 카테고리 분류, 표 구조·오타 대응 성분 추출 테스트."""
import base64
import json

import fakeredis
import numpy as np
import pytest

from app import tasks
from app.vision.ocr_engine import OCRSingletonEngine, classify_product_category


def _box(x1: float, y1: float, x2: float, y2: float):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _make_bare_engine() -> OCRSingletonEngine:
    return object.__new__(OCRSingletonEngine)


def test_layout_title_extractor_coupang_ignores_photo_and_sidepanel():
    engine = _make_bare_engine()
    W, H = 1920, 1080
    ocr_items = [
        (_box(120, 30, 320, 90), "coupang", 0.98),
        (_box(360, 40, 880, 80), "찾고 싶은 상품을 검색해보세요", 0.95),
        (_box(120, 130, 560, 158), "쿠팡 홈 > 식품 > 냉장·냉동식품 > 김치", 0.95),
        (_box(140, 260, 680, 460), "전통명가 100%", 0.97),
        (_box(780, 220, 1360, 256), "[어사김치] 전라도 김장배추 포기김치", 0.96),
        (_box(780, 264, 1180, 298), "국내산 100% 5kg, 1개", 0.96),
        (_box(780, 315, 1150, 342), "***** 44,633개 상품평 · 원산지: 상세설명 참조", 0.95),
        (_box(780, 370, 960, 425), "31,900원", 0.98),
        (_box(780, 440, 1120, 470), "무료배송 내일(토) 도착 보장", 0.96),
        (_box(1580, 190, 1880, 220), "그릭요거트 무가당 단백질 1kg", 0.96),
        (_box(1580, 230, 1700, 260), "6,900원", 0.96),
    ]
    title, category, breadcrumbs = engine.extract_product_title_and_category(ocr_items, W, H)
    assert title == "[어사김치] 전라도 김장배추 포기김치 국내산 100% 5kg, 1개"
    assert category == "food"
    assert len(breadcrumbs) == 1


def test_layout_title_extractor_naver_smartstore_bottom_review_tab_and_shipping_fee():
    """네이버 스마트스토어: 상단에 리뷰 줄이 없고 하단 탭바에 리뷰가 있으며 배송비 3,000원이 함께 있는 경우."""
    engine = _make_bare_engine()
    W, H = 1600, 950
    ocr_items = [
        (_box(80, 30, 260, 65), "스마트스토어", 0.96),
        (_box(180, 240, 650, 600), "프리미엄 수납", 0.95),  # 좌측 사진 배너
        (_box(840, 210, 1380, 246), "모던 와이드 5단 서랍장 800 거실 침실 수납장", 0.97),
        (_box(840, 275, 1060, 325), "109,000원", 0.98),
        (_box(840, 345, 1120, 370), "오늘출발 · 택배배송 3,000원", 0.95),
        (_box(840, 385, 1160, 410), "최대 2,180원 네이버페이 포인트 적립", 0.95),
        (_box(840, 490, 1080, 535), "구매하기", 0.98),
        (_box(840, 780, 1040, 810), "리뷰 2,415", 0.96),  # 하단 탭바 리뷰
    ]
    title, category, _ = engine.extract_product_title_and_category(ocr_items, W, H)
    assert "서랍장" in (title or "")
    assert category == "general_product"


def test_layout_title_extractor_musinsa_wide_gallery_sneakers():
    """무신사/29CM 레이아웃: 좌측 화보가 넓어 우측 구매영역이 x=60% 부근에서 시작하고 모델명 위주인 운동화."""
    engine = _make_bare_engine()
    W, H = 1920, 1080
    ocr_items = [
        (_box(80, 35, 220, 70), "MUSINSA", 0.98),
        (_box(1180, 145, 1520, 170), "신발 > 스니커즈 > 로우탑", 0.95),
        (_box(1180, 195, 1280, 220), "나이키", 0.97),
        (_box(1180, 230, 1680, 266), "에어포스 1 '07 화이트 CW2288-111", 0.97),
        (_box(1180, 285, 1380, 310), "4.9 (8,912)", 0.95),
        (_box(1180, 330, 1390, 376), "139,000원", 0.98),
        (_box(1180, 420, 1450, 450), "사이즈 선택 260mm", 0.95),
        (_box(1180, 500, 1480, 545), "바로구매", 0.98),
    ]
    title, category, _ = engine.extract_product_title_and_category(ocr_items, W, H)
    assert "에어포스" in (title or "")
    assert category == "general_product"


def test_layout_title_extractor_danawa_top_spanning_title():
    """다나와 레이아웃: 사진과 쇼핑몰별 최저가 비교표 위쪽 상단 좌측~중앙에 상품명이 길게 배치됨."""
    engine = _make_bare_engine()
    W, H = 1600, 960
    ocr_items = [
        (_box(100, 35, 240, 70), "danawa", 0.97),
        (_box(140, 165, 980, 206), "LG전자 울트라기어 27GP850 게이밍 모니터 27인치", 0.98),
        (_box(140, 280, 520, 620), "Nano IPS 180Hz", 0.92),
        (_box(620, 280, 860, 330), "399,000원", 0.98),
        (_box(620, 350, 920, 380), "배송비 무료배송", 0.95),
    ]
    title, category, _ = engine.extract_product_title_and_category(ocr_items, W, H)
    assert "모니터" in (title or "")
    assert category == "general_product"


@pytest.mark.parametrize(
    "product_name,breadcrumbs,page_texts,expected",
    [
        ("Apple 2024 맥북 에어 15 M3 256GB", None, None, "general_product"),
        ("한샘 샘베딩 스테디 5단 서랍장 800", None, None, "general_product"),
        ("한샘 샘베딩 스테디 5단 800", ["가구 > 서랍·수납장"], ["방문설치", "E0등급"], "general_product"),
        ("나이키 에어포스 1 07 화이트", None, None, "general_product"),
        ("요넥스 65Z4 배드민 턴화 남성화(MIE) 2026년형", None, ["택배 · 배송비 무료"], "general_product"),
        ("남성 천연 가죽 로퍼 블랙", None, ["무료배송", "무신사"], "general_product"),
        ("뉴발란스 530 스틸그레이", None, None, "general_product"),
        ("클래식 로우탑 모델 X1", None, ["사이즈 선택", "260mm", "갑피", "밑창"], "general_product"),
        ("필립스 대용량 에어프라이어 4.1L", None, None, "general_product"),
        ("드롱기 전자동 커피머신 마그니피카", None, None, "general_product"),
        ("[KF365] 에어프라이어용 생선까스 400g", None, None, "food"),
        ("종가집 포기김치 5kg", None, None, "food"),
        ("라로슈포제 시카플라스트 밤 B5 수분크림 100ml", None, None, "cosmetic"),
        # 안전 가드: 상품명이 모호하거나 일반 단어가 섞여 있어도 화면에 원재료명/소비기한이 있으면 절대 일반상품 종료 금지
        ("프리미엄 선물세트 1호", None, ["소비기한: 전면 표기일까지", "원재료명 및 함량"], "food"),
        ("모호한 신제품 에디션 B", None, None, "unknown"),
    ],
)
def test_classify_product_category(product_name, breadcrumbs, page_texts, expected):
    assert classify_product_category(product_name, breadcrumbs, page_texts) == expected


def test_table_aware_ingredient_extraction_skips_placeholder_and_stops_at_next_row():
    """
    1) 상단 요약표의 '원재료명 및 함량 | 상품 상세설명 참조'는 건너뛰고,
    2) 하단 2단 표에서 세로 중앙 정렬된 th('원재료명 및 함량', y=560) 위쪽부터 시작하는 td(y=500~600)를 모두 읽으며,
    3) 다음 행 th('생산자 및 소재지', y=630) 아래의 주소 텍스트는 섞이지 않고,
    4) '일가루' -> '밀가루', 단독 '일' -> '밀' 오타까지 복원하는지 검증.
    """
    engine = _make_bare_engine()
    ocr_items = [
        # 1번째 앵커: 플레이스홀더 ('상세설명 참조') -> 건너뛰어야 함!
        (_box(120, 200, 320, 226), "원재료명 및 함량", 0.96),
        (_box(360, 200, 580, 226), "상품 상세설명 참조", 0.96),
        # 2번째 앵커: 실제 2단 표 (th가 y=555에 세로 중앙 정렬, 오른쪽 td는 y=495부터 시작!)
        (_box(120, 555, 310, 582), "원제료명 및 함량", 0.95),  # '원제료명' OCR 1글자 오타도 인식해야 함
        (_box(360, 495, 1100, 522), "일가루(일:미국산, 호주산), 돼지고기(국산), 양배추, 대파, 두부(대두),", 0.95),
        (_box(360, 535, 1080, 562), "간장(대두, 일), 참기름, 설탕, 정제소금, L•글루탐산나트름", 0.95),
        (_box(360, 575, 860, 602), "알레르기 유발물질: 일, 대두, 돼지고기 함유", 0.95),
        # 다음 행 th & td (섞이면 안 됨!)
        (_box(120, 635, 310, 660), "생산자 및 소재지", 0.96),
        (_box(360, 635, 880, 660), "서울특별시 강남구 테헤란로 123 한국식품(주)", 0.96),
    ]
    fake_tile = np.zeros((900, 1280, 3), dtype=np.uint8)
    anchor_ys, ingredients = engine.find_all_anchors_and_initial_ingredients(
        [(0, fake_tile)], precomputed_first_tile=ocr_items
    )
    assert len(anchor_ys) == 2
    assert "밀가루" in ingredients
    assert "밀" in ingredients or "밀함유" in ingredients
    assert "돼지고기" in ingredients or "돼지고기함유" in ingredients
    assert "대두" in ingredients
    assert "L-글루탐산나트륨" in ingredients
    assert not any("테헤란로" in x or "상세설명" in x for x in ingredients)


def _patch_fake_redis_eval(fake: fakeredis.FakeRedis) -> None:
    def _fake_eval(script, numkeys, *keys_and_args):
        key = keys_and_args[0]
        status, ing_json, msg, ttl = (
            keys_and_args[1],
            keys_and_args[2],
            keys_and_args[3],
            int(keys_and_args[4]),
        )
        cur = fake.hget(key, "status")
        if status != "success" and cur and cur != "processing":
            return 0
        fake.hset(
            key,
            mapping={
                "status": status,
                "ingredients": ing_json,
                "message": msg,
                "early_exit_flag": "1",
            },
        )
        fake.expire(key, ttl)
        return 1

    fake.eval = _fake_eval


def test_general_product_early_exits_at_phase1_init(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    _patch_fake_redis_eval(fake)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake)

    state = tasks.initialize_session_in_redis("gen-1", "나이키 에어포스 1 운동화 화이트", 139000)
    assert state["status"] == "success"
    assert state["early_exit_flag"] == "1"
    assert state["product_category"] == "general_product"
    assert json.loads(state["ingredients"]) == []

    res = tasks.process_frame_task.run("gen-1", 0, False, base64.b64encode(b"x").decode())
    assert res["skipped"] is True
    assert res["reason"] == "already_success"


def test_general_product_early_exits_via_vision_fallback(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    _patch_fake_redis_eval(fake)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake)
    monkeypatch.setattr(tasks, "decode_image", lambda _: np.zeros((1080, 1920, 3), dtype=np.uint8))

    class _StubEngine:
        def run_ocr(self, img):
            return [
                (_box(780, 220, 1340, 260), "한샘 샘베딩 5단 와이드 서랍장 800", 0.97),
                (_box(780, 320, 1080, 350), "***** 1,240개 상품평", 0.96),
                (_box(780, 380, 980, 430), "129,000원", 0.98),
            ]

        def extract_product_title_and_category(self, items, img_width, img_height):
            return _make_bare_engine().extract_product_title_and_category(items, img_width, img_height)

    monkeypatch.setattr(tasks, "get_ocr_engine", lambda: _StubEngine())

    tasks.initialize_session_in_redis("gen-fb-1", None, None)
    out = tasks.extract_metadata_fallback_task.run("gen-fb-1", base64.b64encode(b"img").decode())
    assert out["early_exit"] is True
    assert out["product_category"] == "general_product"
    assert "서랍장" in (out["product_name"] or "")

    stored = fake.hgetall(tasks.get_session_key("gen-fb-1"))
    assert stored["status"] == "success"
    assert stored["early_exit_flag"] == "1"
    assert stored["product_category"] == "general_product"
    assert json.loads(stored["ingredients"]) == []


def test_food_product_stays_processing_in_phase1(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake)

    state = tasks.initialize_session_in_redis("food-1", "종가집 포기김치 5kg", 31900)
    assert state["status"] == "processing"
    assert state["early_exit_flag"] == "0"
    assert state["product_category"] == "food"
