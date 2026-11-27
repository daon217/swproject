"""최적화된 성분·알레르기 추출기 (엣지 케이스 버그 수정 완료).

개선 및 수정 사항:
1. soup 인자 재사용으로 중복 BeautifulSoup 파싱 제거 + lxml/html.parser 자동 선택.
2. [수정] '[알레르기 정보] 밀, 우유' 처럼 라벨 자체가 대괄호에 감싸진 형태와
   '• [식품정보] 원재료명: ...' 처럼 앞에 말머리가 붙은 형태를 모두 정확히 인식.
3. [수정] '밀, 우유 함유 / 같은 제조시설에서 메밀 사용'처럼 한 문장 안에 직접 함유 절과
   교차오염(TRACE) 절이 섞인 경우에만 TRACE 시작 경계에서 분리하고,
   '같은 제조시설에서 메밀/새우를 사용합니다'는 문장 전체를 trace로 유지해 오분류 원천 차단.
4. <th>/<td> 및 <dt>/<dd> 테이블 구조 직접 탐색(_table_value) 지원.
"""
import json
import re

try:
    import lxml  # noqa: F401
    _HTML_PARSER = "lxml"
except ImportError:
    _HTML_PARSER = "html.parser"

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
    "복숭아": "복숭아 황도 백도 천도복숭아 peach 桃",
    "토마토": "토마토 tomato 番茄 トマト",
    "아황산류": "아황산 이산화황 이산화항 아황산나트륨 중아황산 sulfite sulfites sulphite sulphites sulfur dioxide 亚硫酸盐 二氧化硫 亜硫酸塩",
    "호두": "호두 walnut walnuts 核桃 くるみ",
    "닭고기": "닭고기 닭 계육 chicken 鸡肉 鶏肉",
    "쇠고기": "쇠고기 소고기 우육 beef 牛肉",
    "오징어": "오징어 squid 鱿鱼 イカ",
    "조개류": "조개 굴 전복 홍합 바지락 가리비 골뱅이 소라 꼬막 백합 재첩 clam clams oyster oysters mussel mussels scallop abalone whelk 牡蛎 贝 貝 牡蠣",
    "잣": "잣 pine nut pine nuts 松子 松の実",
    "참깨*": "참깨 깨 sesame 芝麻 ごま 胡麻",
    "견과류*": "견과 아몬드 캐슈 헤이즐넛 피스타치오 마카다미아 피칸 브라질너트 almond almonds cashew hazelnut pistachio macadamia pecan nuts 坚果 ナッツ",
    "생선*": "생선 연어 참치 가다랑어 황다랑어 다랑어 명태 대구 멸치 조기 어육 fish salmon tuna bonito skipjack pollock cod anchovy 鱼 魚 鮭",
}
_ASCII = re.compile(r"^[A-Za-z ]+$")
PHRASES = ("pine nuts", "pine nut", "sulfur dioxide")


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
                parts.append(rf"(?<![가-힣]){re.escape(t)}(?:(?![가-힣])|(?=[은는이가을를의도과와에로]))")
            else:
                parts.append(re.escape(t))
        out[canon] = re.compile("|".join(parts), re.I)
    return out


PATTERNS = _compile()
TRACE = re.compile(
    r"같은\s*(제조)?\s*시설|동일\s*(제조|시설|설비)|같은\s*설비|혼입|발생\s*가능성|교차|"
    r"may contain|traces? of|facility|shared|可能含有|可能混入|同一(生产|车间)|共线|"
    r"同じ(製造|工場)|混入する可能性|含まれている可能性",
    re.I,
)
# 한 문장 앞절에 직접 함유가 있고 뒤에 구분자(/, |, ※, 단 등)와 함께 교차오염 절이 이어지는 패턴
_MIXED_TRACE_SPLIT = re.compile(
    r"^(.*?(?:함유|포함|원재료|알레르기|allergens?|contains?)[^/|※]*?)"
    r"(?:\s*[/|※]\s*|\s*,\s*(?=(?:이\s*제품은|본\s*제품은|같은|동일|may\s+contain|traces?\s+of)))"
    r"(.+)$",
    re.I,
)

NONE = re.compile(r"해당\s*없음|없음|no allergens?|none|无|なし", re.I)
POINTER = re.compile(r"참조|참고|상세\s*(페이지|설명)|이미지|see (image|description)", re.I)

_ING_CORE = r"원재료명?(?:\s*및\s*함량)?|원료명|ingredients?|配料|成分|原材料"
_ALG_CORE = r"알레르기\s*(?:유발\s*물질|정보)?|알러지\s*(?:유발\s*물질|정보)?|알레르기|알러지|allergens?(?: information)?|allergy|过敏原|アレルギー"
# 라벨 자체가 아닌 말머리 태그([식품정보] 등)와 불릿 기호만 건너뛰고, [알레르기 정보]처럼 대괄호로 감싼 라벨도 매칭
_PREFIX = rf"(?:[\s•·▪▫▶▷◆◇■□※★☆*\-–—]+|\[(?!\s*(?:{_ING_CORE}|{_ALG_CORE})\s*\])[^\]]{{1,20}}\]\s*)*"

ING_LABEL = re.compile(rf"^{_PREFIX}\[?\s*({_ING_CORE})\s*\]?\s*[:：]?\s*(.*)$", re.I)
ALG_LABEL = re.compile(rf"^{_PREFIX}\[?\s*({_ALG_CORE})\s*\]?\s*[:：]?\s*(.*)$", re.I)
ICON = re.compile(r"/ico|logo|\.svg|sprite|banner|btn", re.I)
MORE = re.compile(r"^-|함유|제조|알레르기|혼입|may contain|facility|可能|含有", re.I)


def _iter_clauses(text):
    """문장 단위로 먼저 나눈 뒤, 한 문장 안에 함유 절과 교차오염 절이 구분자로 섞여 있을 때만 추가 분리."""
    for seg in re.split(r"[.;\n。]", text or ""):
        seg = seg.strip()
        if not seg:
            continue
        if TRACE.search(seg):
            m = _MIXED_TRACE_SPLIT.match(seg)
            if m and TRACE.search(m.group(2)) and not TRACE.search(m.group(1)):
                yield m.group(1), False
                yield m.group(2), True
                continue
            yield seg, True
        else:
            yield seg, False


def find_allergens(text):
    """-> (contains, trace) 정규화된 알러지 이름 집합."""
    contains, trace = set(), set()
    for clause, is_trace in _iter_clauses(text):
        target = trace if is_trace else contains
        for canon, pat in PATTERNS.items():
            if pat.search(clause):
                target.add(canon)
    return contains, trace - contains


def _lines(soup):
    return [x.strip() for x in soup.get_text("\n").split("\n") if x.strip()]


def _value(lines, rx, more=False):
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if m:
            inline = (m.group(m.lastindex) or "").strip()
            got = [inline] if inline else []
            j = i + 1
            while j < len(lines) and not ING_LABEL.match(lines[j]) and not ALG_LABEL.match(lines[j]) and j - i <= 4:
                if got and not (more and MORE.search(lines[j])):
                    break
                got.append(lines[j])
                j += 1
                if not more:
                    break
            if got:
                return " . ".join(got)
    return None


def _table_value(soup, rx):
    """<th>/<td> 및 <dt>/<dd> 구조에서 라벨에 대응하는 값을 직접 추출한다."""
    for label in soup.find_all(["th", "dt"]):
        txt = " ".join(label.get_text(" ", strip=True).split())
        if not txt or len(txt) > 95:
            continue
        # 공정위 상품정보제공고시 괄호 부연설명 제거 후 라벨 매칭 지원
        cleaned = re.sub(r"\s*\([^)]{1,60}\)\s*$", "", txt)
        if rx.match(txt) or rx.match(cleaned):
            sib = label.find_next_sibling(["td", "dd"])
            if sib:
                val = " ".join(sib.get_text(" ", strip=True).split())
                if val:
                    return val
    return None


def _embedded_spec_value(soup, rx):
    """Nuxt(__NUXT_DATA__) / Next(__NEXT_DATA__) 등 인라인 JSON 배열·객체에 들어있는 상품정보고시 항목 추출."""
    for sc in soup.find_all("script"):
        sid = sc.get("id") or ""
        stype = sc.get("type") or ""
        if sid not in ("__NUXT_DATA__", "__NEXT_DATA__") and stype != "application/json":
            continue
        raw = sc.string or ""
        if not raw or len(raw) > 600_000 or ("원재료" not in raw and "알레르기" not in raw):
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, list):
            for i, item in enumerate(data[:-1]):
                if isinstance(item, str) and len(item) <= 95:
                    cleaned = re.sub(r"\s*\([^)]{1,60}\)\s*$", "", item.strip())
                    if rx.match(item.strip()) or rx.match(cleaned):
                        nxt = data[i + 1]
                        if isinstance(nxt, str) and nxt.strip():
                            return nxt.strip()
    return None


def extract_allergen_info(html, soup=None, *, parser=None):
    """status: read | read_empty | image_only | unreadable."""
    if soup is None:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, parser or _HTML_PARSER)
    lines = _lines(soup)
    ing = _value(lines, ING_LABEL) or _table_value(soup, ING_LABEL) or _embedded_spec_value(soup, ING_LABEL)
    alg = _value(lines, ALG_LABEL, more=True) or _table_value(soup, ALG_LABEL) or _embedded_spec_value(soup, ALG_LABEL)
    ing_text = None if (ing is None or POINTER.search(ing) and len(ing) < 40) else ing
    alg_text = alg
    contains, trace = find_allergens(" ".join(x for x in (ing_text, alg_text) if x))
    pointer = any(x and POINTER.search(x) for x in (ing, alg))
    if pointer:
        imgs = [i.get("src") or i.get("data-src") or "" for i in soup.find_all("img")]
        imgs = [s for s in dict.fromkeys(imgs) if s.startswith("http") and not ICON.search(s)][1:11]
    else:
        imgs = []
    if contains or trace:
        status = "read"
    elif alg_text and NONE.search(alg_text) and not POINTER.search(alg_text):
        status = "read_empty"
    elif pointer or ing_text:
        status = "image_only" if pointer and not ing_text else "unreadable"
    else:
        status = "unreadable"
    return dict(
        ingredient_text=ing_text,
        allergen_text=alg_text,
        allergens_contains=sorted(contains),
        allergens_trace=sorted(trace),
        ingredient_images=imgs,
        allergen_status=status,
    )


def match(user_allergies, info):
    mine = set()
    for a in user_allergies:
        hit = [c for c, p in PATTERNS.items() if p.search(a)]
        mine |= set(hit or [a])
    d, c = mine & set(info["allergens_contains"]), mine & set(info["allergens_trace"])
    if d:
        return "danger", sorted(d)
    if c:
        return "caution", sorted(c)
    if info["allergen_status"] in ("image_only", "unreadable"):
        return "unknown", []
    return "clear", []
