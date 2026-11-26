"""#62 회귀: 성분 정제가 알레르기 근거를 지우지 않는다(OCR 엔진 없이 정제 함수만)."""
from app.vision.ocr_engine import OCRSingletonEngine

clean = OCRSingletonEngine.clean_ingredient_text


def test_bracket_contents_are_kept_and_origins_dropped():
    out = clean('원재료명: 소맥분(밀:미국산), 대두유(대두), 버터(우유, 대두), 식물성유지(팜유 10%)')
    for word in ('밀', '대두유', '대두', '우유', '팜유'):
        assert word in out
    assert '미국산' not in out


def test_single_char_allergens_and_acids_survive():
    out = clean('게, 잣, 굴, 아황산, 구연산, 국산')
    assert ['게', '잣', '굴', '아황산', '구연산'] == out


def test_allergen_notice_and_cross_contact_are_not_dropped():
    out = clean('알레르기 유발물질: 대두, 밀 함유. 같은 제조시설에서 땅콩을 사용한 제품과 같은 시설에서 제조')
    assert '대두' in out and '밀함유' in out
    assert any('땅콩' in t for t in out)
    assert not any('소비자' in t for t in clean('소비자 상담실 080-000-0000, 밀'))
