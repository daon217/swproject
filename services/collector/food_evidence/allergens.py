"""상품 페이지에서 성분·알레르기 정보를 뽑고(extract_allergen_info), 사용자 알러지와 대조한다(match).

원칙: 못 읽은 것을 '없음'으로 취급하지 않는다. status가 image_only/unreadable이면 대조 결과는 항상 unknown(확인 필요).
shortcut: 사전은 식약처 19종 + 참깨/견과류/생선, 한·영·중·일 대표어만. 최신 고시와 대조하고 누락 단어는 계속 추가한다.
"""
import re

# 식약처 표시대상 19종(기억 기준, 고시와 대조 필요) + 해외 상품용 3종(*)
SYN = {
    "알류": "알류 난류 계란 달걀 egg eggs 蛋 鸡蛋 卵 玉子 たまご",
    "우유": "우유 유제품 탈지분유 분유 전지분유 유청 카제인 락토 치즈 버터 생크림 유크림 milk whey casein lactose butter cheese dairy 牛奶 乳制品 牛乳 乳製品 乳成分",
    "메밀": "메밀 buckwheat 荞麦 蕎麦 そば",
    "땅콩": "땅콩 peanut peanuts 花生 落花生 ピーナッツ",
    "대두": "대두 콩 soy soya soybean soybeans 大豆 黄豆",
    "밀": "밀 밀가루 소맥 글루텐 wheat gluten 小麦 面粉 小麦粉",
    "고등어": "고등어 mackerel 鲭鱼 青花鱼 さば 鯖",
    "게": "게 꽃게 대게 crab 蟹 螃蟹 カニ",
    "새우": "새우 shrimp prawn 虾 海老 えび エビ",
    "돼지고기": "돼지고기 돈육 돼지 pork 猪肉 豚肉",
    "복숭아": "복숭아 peach 桃",
    "토마토": "토마토 tomato 番茄 トマト",
    "아황산류": "아황산 이산화황 이산화항 아황산나트륨 중아황산 sulfite sulfites sulphite sulphites sulfur dioxide 亚硫酸盐 二氧化硫 亜硫酸塩",
    "호두": "호두 walnut walnuts 核桃 くるみ",
    "닭고기": "닭고기 닭 계육 chicken 鸡肉 鶏肉",
    "쇠고기": "쇠고기 소고기 우육 beef 牛肉",
    "오징어": "오징어 squid 鱿鱼 イカ",
    "조개류": "조개 굴 전복 홍합 바지락 가리비 clam clams oyster oysters mussel mussels scallop abalone 牡蛎 贝 貝 牡蠣",
    "잣": "잣 pine nut pine nuts 松子 松の実",
    "참깨*": "참깨 깨 sesame 芝麻 ごま 胡麻",
    "견과류*": "견과 아몬드 캐슈 헤이즐넛 피스타치오 almond almonds cashew hazelnut pistachio nuts 坚果 ナッツ",
    "생선*": "생선 연어 참치 fish salmon tuna 鱼 魚 鮭",
}
_ASCII = re.compile(r"^[A-Za-z ]+$")


PHRASES = ("pine nuts", "pine nut", "sulfur dioxide")  # 공백이 들어간 영어 구절


def _compile():
    out = {}
    for canon, words in SYN.items():
        toks = words.split()
        for ph in PHRASES:
            if ph in words:
                toks = [w for w in toks if w not in ph.split()] + [ph]
        parts = []
        for t in toks:
            if _ASCII.match(t):
                parts.append(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])")
            elif len(t) == 1 and re.match(r"[가-힣]$", t):
                # 한 글자 단어는 앞에 한글이 오면 제외, 뒤에는 조사만 허용 ('밀봉'의 '밀', '소굴'의 '굴' 오탐 방지)
                parts.append(rf"(?<![가-힣]){re.escape(t)}(?:(?![가-힣])|(?=[은는이가을를의도과와에로]))")
            else:
                parts.append(re.escape(t))
        out[canon] = re.compile("|".join(parts), re.I)
    return out


PATTERNS = _compile()
TRACE = re.compile(r"같은\s*(제조)?\s*시설|동일\s*(제조|시설|설비)|같은\s*설비|혼입|발생\s*가능성|교차|may contain|traces? of|facility|shared|可能含有|可能混入|同一(生产|车间)|共线|同じ(製造|工場)|混入する可能性|含まれている可能性", re.I)
NONE = re.compile(r"해당\s*없음|없음|no allergens?|none|无|なし", re.I)
POINTER = re.compile(r"참조|참고|상세\s*(페이지|설명)|이미지|see (image|description)", re.I)
ING_LABEL = re.compile(r"^(원재료명?(\s*및\s*함량)?|원료명|ingredients?|配料|成分|原材料)\s*[:：]?\s*(.*)$", re.I)
ALG_LABEL = re.compile(r"^(알레르기\s*정보|알러지\s*정보|알레르기|알러지|allergens?( information)?|allergy|过敏原|アレルギー)\s*[:：]?\s*(.*)$", re.I)
ICON = re.compile(r"/ico|logo|\.svg|sprite|banner|btn", re.I)


def find_allergens(text):
    """-> (contains, trace) 정규화된 알러지 이름 집합. 교차오염 문구가 있는 문장은 trace로 분리."""
    contains, trace = set(), set()
    for seg in re.split(r"[.;\n。]", text or ""):
        target = trace if TRACE.search(seg) else contains
        for canon, pat in PATTERNS.items():
            if pat.search(seg):
                target.add(canon)
    return contains, trace - contains


def _lines(soup):
    return [x.strip() for x in soup.get_text("\n").split("\n") if x.strip()]


MORE = re.compile(r"^-|함유|제조|알레르기|혼입|may contain|facility|可能|含有", re.I)


def _value(lines, rx, more=False):
    """라벨 줄 다음 값을 돌려준다(같은 줄에 값이 있으면 그것). more면 이어지는 '함유/제조시설' 줄도 붙인다."""
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if m:
            inline = (m.group(m.lastindex) or "").strip()
            got = [inline] if inline else []
            j = i + 1
            while j < len(lines) and not ING_LABEL.match(lines[j]) and not ALG_LABEL.match(lines[j]) and j - i <= 4:
                if got and not (more and MORE.search(lines[j])):
                    break
                got.append(lines[j]); j += 1
                if not more:
                    break
            if got:
                return " . ".join(got)
    return None


def extract_allergen_info(html):
    """status: read(알러지 항목 읽음) | read_empty(없다고 명시) | image_only(이미지 참조뿐) | unreadable(못 찾음)."""
    from bs4 import BeautifulSoup  # 사전 대조(find_allergens)만 쓰는 쪽은 bs4 없이 import 가능하게
    soup = BeautifulSoup(html, "lxml")
    lines = _lines(soup)
    ing, alg = _value(lines, ING_LABEL), _value(lines, ALG_LABEL, more=True)
    ing_text = None if (ing is None or POINTER.search(ing) and len(ing) < 40) else ing
    alg_text = alg
    contains, trace = find_allergens(" ".join(x for x in (ing_text, alg_text) if x))
    pointer = any(x and POINTER.search(x) for x in (ing, alg))
    imgs = [i.get("src") or i.get("data-src") or "" for i in soup.find_all("img")]
    imgs = [s for s in dict.fromkeys(imgs) if s.startswith("http") and not ICON.search(s)][1:11] if pointer else []
    if contains or trace:
        status = "read"
    elif alg_text and NONE.search(alg_text) and not POINTER.search(alg_text):
        status = "read_empty"
    elif pointer or ing_text:
        status = "image_only" if pointer and not ing_text else "unreadable"  # 글자는 있는데 사전에 걸리는 단어가 없으면 못 읽은 것으로 본다
    else:
        status = "unreadable"
    return dict(ingredient_text=ing_text, allergen_text=alg_text, allergens_contains=sorted(contains),
                allergens_trace=sorted(trace), ingredient_images=imgs, allergen_status=status)


def match(user_allergies, info):
    """-> (level, 대상). level: danger(직접 함유) > caution(교차오염 가능) > unknown(확인 필요) > clear(성분표에서 발견 안 됨, 안전 보장 아님)."""
    mine = set()
    for a in user_allergies:
        hit = [c for c, p in PATTERNS.items() if p.search(a)]
        mine |= set(hit or [a])  # 사전에 없는 입력도 그대로 비교(조용히 버리지 않음)
    d, c = mine & set(info["allergens_contains"]), mine & set(info["allergens_trace"])
    if d:
        return "danger", sorted(d)
    if c:
        return "caution", sorted(c)
    if info["allergen_status"] in ("image_only", "unreadable"):
        return "unknown", []
    return "clear", []
