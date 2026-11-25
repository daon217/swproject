from services.collector.food_evidence.allergens import extract_allergen_info, find_allergens, match


def page(*lines):
    return "<html><body>" + "".join(f"<div>{x}</div>" for x in lines) + "</body></html>"


def test_synonyms_multilang():
    c, _ = find_allergens("Contains: Milk, wheat gluten; 含有鸡蛋 花生 エビ, 탈지분유, 달걀")
    assert {"우유", "밀", "알류", "땅콩", "새우"} <= c


def test_short_word_no_false_hit():
    assert find_allergens("밀봉 포장, 소굴")[0] == set()  # 밀/굴이 다른 단어 속에 있을 때
    assert find_allergens("밀, 굴 함유")[0] == {"밀", "조개류"}


def test_trace_separate():
    c, t = find_allergens("우유 함유. 고등어, 새우를 사용한 제품과 같은 제조시설에서 제조")
    assert c == {"우유"} and t == {"고등어", "새우"}


def test_kurly_style_read_and_image_only():
    r = extract_allergen_info(page("원재료명 및 함량", "상품설명 및 상품이미지 참조", "알레르기정보", "- 우유, 대두 함유"))
    assert r["allergen_status"] == "read" and r["allergens_contains"] == ["대두", "우유"]
    r = extract_allergen_info(page("원재료명 및 함량", "상품설명 및 상품이미지 참조"))
    assert r["allergen_status"] == "image_only"
    assert extract_allergen_info(page("아무 정보 없음 페이지"))["allergen_status"] == "unreadable"


def test_read_empty_and_noise():
    assert extract_allergen_info(page("알레르기정보", "해당없음"))["allergen_status"] == "read_empty"
    assert extract_allergen_info(page("알레르기정보", "[h541] 마르게리따 파스타"))["allergen_status"] == "unreadable"


def test_match_never_says_clear_when_unknown():
    unk = extract_allergen_info(page("원재료명", "상품설명 및 상품이미지 참조"))
    assert match(["땅콩"], unk) == ("unknown", [])
    ok = extract_allergen_info(page("알레르기정보", "우유 함유"))
    assert match(["땅콩"], ok) == ("clear", [])
    assert match(["우유", "땅콩"], ok) == ("danger", ["우유"])
    assert match(["Milk"], ok)[0] == "danger"  # 영어 입력도 정규화
    tr = extract_allergen_info(page("알레르기정보", "우유 함유. 땅콩과 같은 제조시설"))
    assert match(["땅콩"], tr) == ("caution", ["땅콩"])
