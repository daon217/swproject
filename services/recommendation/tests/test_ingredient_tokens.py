"""#65 회귀: 표 머리말·'함유' 접미사가 한 글자 알레르기 감지를 막지 않는다."""
from services.recommendation.allergens import detect, split_ingredients


def test_header_and_suffix_are_stripped():
    assert split_ingredients('원재료명: 게, 밀 함유, 쌀가루(국산)') == ['게', '밀', '쌀가루', '국산']
    assert set(detect(split_ingredients('원재료명: 게, 밀 함유'))) == {'crab', 'wheat'}
    assert set(detect(['알레르기 정보: 우유, 대두 함유'])) == {'milk', 'soy'}


def test_no_new_false_positives():
    assert detect(['밀봉 포장']) == {}
    assert set(detect(['메밀가루'])) == {'buckwheat'}
