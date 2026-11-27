"""
[ocr_engine.py]
PaddleOCR(`lang='korean'`) / Windows Native OCR 싱글톤(Singleton) 엔진과,
1) Phase 1 멀티 쇼핑몰 레이아웃 적응형 상품명 추출 및 다중 신호 카테고리 분류(식품/화장품 vs 일반 상품)
2) Phase 2 표 구조·오타 허용 앵커(Anchor) 키워드 탐색 및 다중 앵커 후보 반환
3) 전처리된 ROI 이미지에서 정규표현식(Regex) + 한국어 OCR 오타 보정 기반 성분표 정제 로직을 담당합니다.
"""

import logging
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


# 한 글자로 표기되는 알레르기 원료(성분표의 '밀', '게' 등). 1글자 노이즈 제거에서 제외한다(#62).
ALLERGEN_SINGLE_CHARS = frozenset({"밀", "게", "잣", "굴", "깨", "콩"})
# '…산'으로 끝나지만 원산지가 아닌 성분(아황산류는 알레르기 표시 대상).
ACID_INGREDIENTS = frozenset(
    {"아황산", "구연산", "젖산", "초산", "사과산", "주석산", "인산", "호박산", "규산", "빙초산", "아스코르빈산", "글루탐산", "폴리감마글루탐산", "히알루론산"}
)

# ==============================================================================
# Phase 1: 전 쇼핑몰 호환 레이아웃 기반 상품명 추출 & 다중 신호 카테고리 분류 규칙
# ==============================================================================
_MAIN_PRICE_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\b\d{4,8})\s*원|₩\s*\d{1,3}(?:,\d{3})+")
_SECONDARY_PRICE_NOISE_RE = re.compile(
    r"배송비|택배비|반품비|교환비|도서산간|적립|포인트|캐시|머니|쿠폰|최대\s*\d|할인\s*받기|"
    r"100\s*g|10\s*g|100\s*ml|10\s*ml|1\s*개당|개당|캡슐당|정당|포당|매당|원\s*/",
    re.IGNORECASE,
)
_REVIEW_ANCHOR_RE = re.compile(
    r"상품평|명이상\s*구매|구매했|\d[\d,]*\s*개?\s*(?:리뷰|상품평|후기|구매평)|"
    r"리뷰\s*\(?\s*\d|별점|평점\s*\d|★{1,}\s*[0-5]\.\d|[*★☆]\s*[0-5]\.\d|\*{3,}|★{2,}|"
    r"\b[345]\.\d\s*\(\s*(?:최근|\d[\d,]*)|최근\s*\d+개월|"
    r"원산지\s*[:：•·]"
)
_BUY_BUTTON_RE = re.compile(
    r"장바구니|바로\s*구매|구매하기|선물하기|오늘드림|정기배송\s*신청|주문하기",
    re.IGNORECASE,
)
_BREADCRUMB_RE = re.compile(r"[가-힣A-Za-z0-9·/]+\s*(?:[>›〉≫▸]|->)\s*[가-힣A-Za-z0-9·/]+")

_NON_TITLE_LINE_RE = re.compile(
    r"^\s*[\d,.\s~+\-×x*()%/]+(?:원|%|개|점|건|명|위|차|일|시간|분|초|p|P|원씩)?\s*$|"
    r"^\s*\d+(?:\.\d+)?\s*(?:g|kg|ml|l|개|입|팩|봉|병|매|정|포|박스|세트)\s*[x×*]\s*\d+\s*(?:개|입|팩|봉|병|박스)?\s*$|"
    r"https?://|www\.|\.co\.kr|\.com\b|localhost|127\.0\.0\.1|"
    r"100\s*g당|10\s*g당|100\s*ml당|10\s*ml당|1\s*개당|최저\s*단위가|단위가격|"
    r"와우쿠폰|와우회원|쿠폰할인|쿠폰적용가|일반할인가|즉시할인가|최대혜택가|혜택가|판매가|정상가|정가|할인가|카드할인|청구할인|무이자|할부|적립금|캐시\s*적립|최대\s*\d[\d,]*\s*(?:원|%|p|점)|"
    r"무료배송|무료반품|배송비|택배비|로켓배송|로켓프레시|로켓와우|로켓직구|판매자로켓|판매자배송|샛별배송|낮배송|새벽배송|오늘출발|오늘드림|당일발송|당일출고|빠른배송|방문설치|직접설치|화물택배|착불|"
    r"내일\s*\(?[월화수목금토일]?\)?.*도착|모레.*도착|도착\s*예정|도착\s*보장|출발\s*예정|발송\s*예정|"
    r"장바구니|바로\s*구매|구매하기|선물하기|찜하기|공유하기|톡톡문의|문의하기|비교하기|모든\s*옵션|옵션\s*보기|옵션\s*선택|색상\s*선택|사이즈\s*선택|수량\s*선택|필수\s*옵션|추가\s*상품|다른\s*판매자|판매자\s*[:：]|브랜드관|공식스토어|공식몰|스토어\s*찜|알림받기|"
    r"상품평|명이상\s*구매|구매했|별점|평점|★{2,}|\*{3,}|[*★☆]\s*[0-5]\.\d|최근\s*\d+개월|원산지\s*[:：•·]|^\s*원산지\b|상세설명\s*참조|상세페이지\s*참조|개당\s*중량|"
    r"로그인|회원가입|고객센터|마이페이지|마이쿠팡|주문조회|카테고리|전체메뉴|검색해보세요|검색어를\s*입력|즐겨찾기|북마크|새\s*탭|입점신청|사업자정보|"
    r"커뮤니티\s+쇼핑|베스트\s+신상품|랭킹\s+업데이트|이벤트\s+기획전|품절임박|재입고\s*알림|"
    r"꿀픽|kkulpick|gemini에게|사이드\s*패널|추천\s*상품\s*보기|성분표\s*탐색|"
    r"^(?:coupang|쿠팡|naver|네이버|네이버쇼핑|스마트스토어|브랜드스토어|npay|네이버페이|마켓컬리|컬리|kurly|11번가|11st|g마켓|gmarket|옥션|auction|ssg|신세계몰|이마트몰|무신사|musinsa|올리브영|olive\s*young|오늘의집|29cm|w컨셉|wconcept|에이블리|지그재그|크림|kream|다나와|danawa|에누리|롯데온|lotteon|현대hmall|gs\s*shop|cj온스타일|다이소몰|아이허브|iherb|알리익스프레스|테무|temu|아마존|amazon|wow|new|best|hot|sale|hit|md추천|단독|특가|무배|오늘특가|타임특가)$",
    re.IGNORECASE,
)

# 명확한 식품/화장품 표기 신호 (화면에 이 문구가 있으면 절대 일반 상품으로 조기 종료하지 않음!)
_STRICT_INGREDIENT_DOMAIN_GUARD_RE = re.compile(
    r"원재료명|원재료\s*및\s*함량|전성분|화장품법에\s*따라|화장품책임판매업자|식품의\s*유형|품목보고번호|"
    r"영양정보|영양성분|소비기한|유통기한|냉장보관|냉동보관|해썹|HACCP|알레르기\s*유발",
    re.IGNORECASE,
)

_COSMETIC_CATEGORY_RE = re.compile(
    r"화장품|뷰티|스킨케어|미용|스킨|토너|로션|에센스|세럼|앰플|크림(?!치즈|소스|스프|수프|파스타|우동|빵|떡|케이크)|"
    r"수분크림|영양크림|아이크림|선크림|썬크림|선블록|선스틱|선쿠션|자외선\s*차단|"
    r"클렌징|클렌저|폼클렌징|폼클렌저|클렌징폼|클렌징오일|클렌징워터|클렌징밤|필링젤|스크럽|"
    r"샴푸|린스|컨디셔너|트리트먼트|헤어에센스|헤어오일|헤어팩|염색약|새치염색|바디워시|바디로션|바디크림|바디오일|바디미스트|"
    r"핸드크림|핸드워시|풋크림|립밤|립스틱|립틴트|틴트|립글로스|파운데이션|쿠션팩트|비비크림|컨실러|프라이머|파우더|"
    r"아이섀도우|섀도우|아이라이너|마스카라|아이브로우|블러셔|하이라이터|쉐딩|마스크팩|시트팩|패드|토너패드|"
    r"향수|퍼퓸|오드퍼퓸|오드뚜왈렛|코롱|데오드란트|네일|매니큐어|제모크림|"
    r"세탁세제|액체세제|캡슐세제|주방세제|식기세척기세제|섬유유연제|표백제|탈취제|방향제|디퓨저|치약|가글|구강청결제|물티슈|비누|입욕제"
)

_FOOD_CATEGORY_RE = re.compile(
    r"식품|신선식품|가공식품|건강기능식품|건강식품|로켓프레시|샛별배송|밀키트|반찬|도시락|간편식|"
    r"김치|배추김치|포기김치|총각김치|깍두기|겉절이|열무김치|파김치|백김치|보쌈김치|동치미|장아찌|단무지|쌈무|젓갈|명란|"
    r"라면|컵라면|봉지라면|국수|쌀국수|칼국수|수제비|파스타|스파게티|우동|냉면|쫄면|비빔면|소바|메밀면|당면|짜장|짬뽕|만두|교자|딤섬|떡볶이|떡국|가래떡|순대|볶음밥|비빔밥|덮밥|주먹밥|김밥|유부초밥|오니기리|"
    r"과자|스낵|쿠키|비스킷|크래커|웨하스|포테이토칩|감자칩|고구마칩|초코칩|나쵸|팝콘|초콜릿|초코|젤리|구미|사탕|캔디|카라멜|자일리톨껌|풍선껌|양갱|약과|한과|강정|"
    r"아이스크림|빙수|샤베트|케이크|베이커리|카스텔라|마카롱|휘낭시에|마들렌|도넛|머핀|와플|팬케이크|식빵|모닝빵|베이글|크루아상|크로와상|바게트|호빵|찐빵|호떡|붕어빵|샌드위치|햄버거|피자|핫도그|"
    r"즉석밥|햇반|찌개|김치찌개|된장찌개|부대찌개|청국장|전골|갈비탕|곰탕|사골|설렁탕|삼계탕|감자탕|육개장|해장국|추어탕|국밥|미역국|수프|스프|전복죽|호박죽|단팥죽|야채죽|소고기죽|닭죽|즉석죽|"
    r"돈까스|돈가스|치킨까스|생선까스|탕수육|깐풍기|치킨|너겟|텐더|핫윙|떡갈비|동그랑땡|핫바|어묵바|크로켓|고로케|튀김|"
    r"소스|토마토소스|크림소스|굴소스|칠리소스|양념|양념장|간장|진간장|국간장|된장|고추장|쌈장|청국장가루|케첩|케찹|마요네즈|머스타드|드레싱|식초|발사믹|"
    r"식용유|참기름|들기름|올리브유|올리브오일|카놀라유|포도씨유|해바라기유|아보카도오일|설탕|원당|소금|천일염|맛소금|후추|고춧가루|깨소금|볶음참깨|카레|짜장분말|밀가루|박력분|강력분|중력분|부침가루|튀김가루|빵가루|전분|물엿|올리고당|조청|"
    r"딸기잼|사과잼|블루베리잼|과일잼|카야잼|스프레드|땅콩버터|피넛버터|아몬드버터|헤이즐넛|누텔라|시럽|메이플시럽|벌꿀|아카시아꿀|잡화꿀|"
    r"우유|멸균우유|락토프리|두유|베지밀|오트밀크|귀리음료|아몬드브리즈|아몬드밀크|코코넛밀크|요거트|요구르트|그릭요거트|치즈|모짜렐라|체다치즈|크림치즈|버터|기버터|마가린|분유|생크림|휘핑크림|연유|"
    r"커피|원두|드립백|캡슐커피|믹스커피|아메리카노|콜드브루|라떼|에스프레소(?!머신)|음료|이온음료|주스|쥬스|에이드|스무디|식혜|수정과|콤부차|탄산수|탄산음료|콜라|사이다|생수|미네랄워터|녹차|홍차|보리차|옥수수수염차|헛개차|둥굴레차|캐모마일|페퍼민트|루이보스|히비스커스|유자차|생강차|티백|"
    r"견과|견과류|하루견과|땅콩|아몬드|호두|캐슈넛|피스타치오|마카다미아|피칸|브라질너트|가평잣|볶음잣|해바라기씨|호박씨|건포도|크랜베리|건자두|푸룬|시리얼|그래놀라|뮤즐리|오트밀|프로틴바|단백질바|에너지바|"
    r"소시지|비엔나|후랑크|베이컨|스팸|통조림햄|참치캔|연어캔|골뱅이캔|옥수수캔|어묵|유부|두부|순두부|콩나물|숙주|계란|달걀|구운란|반숙란|메추리알|"
    r"정육|한우|소고기|쇠고기|돼지고기|삼겹살|목살|항정살|갈비|LA갈비|불고기|차돌박이|우삼겹|등심|안심|채끝|양갈비|닭가슴살|닭다리살|닭안심|닭볶음탕|생닭|오리고기|훈제오리|막창|곱창|육포|"
    r"백미|현미|찹쌀|흑미|햅쌀|경기미|잡곡|혼합곡|보리쌀|귀리|메밀|퀴노아|렌틸콩|병아리콩|서리태|검은콩|"
    r"과일|사과|신고배|나주배|황금배|딸기|블루베리|복숭아|자두|포도|샤인머스캣|바나나|감귤|한라봉|천혜향|오렌지|자몽|레몬|키위|망고|수박|멜론|참외|아보카도|토마토|방울토마토|"
    r"채소|야채|샐러드|고구마|감자|양파|대파|쪽파|마늘|다진마늘|생강|고추|파프리카|오이|당근|세척무|무말랭이|배추|양배추|브로콜리|상추|깻잎|시금치|부추|버섯|새송이|팽이버섯|표고버섯|"
    r"수산물|해산물|생선|오징어|진미채|쥐포|새우|칵테일새우|멸치|고등어|삼치|연어|훈제연어|갈치|조기|굴비|명태|황태|북어|코다리|대구|문어|낙지|쭈꾸미|주꾸미|전복|생굴|통영굴|홍합|바지락|조개|꽃게|간장게장|양념게장|조미김|도시락김|곱창김|재래김|파래김|구운김|김자반|미역|다시마|육수|코인육수|다시팩|"
    r"영양제|비타민|멀티비타민|유산균|프로바이오틱스|락토핏|오메가3|루테인|밀크씨슬|홍삼|정관장|녹용|침향|흑염소|콜라겐|히알루론산정|마그네슘|칼슘|철분|아연|엽산|아르기닌|프로폴리스|효소|단백질쉐이크|프로틴|양배추즙|사과즙|배즙|배도라지|레몬즙"
)

_GENERAL_PRODUCT_RE = re.compile(
    r"가전디지털|디지털/가전|컴퓨터|데스크탑|데스크톱|일체형PC|미니PC|노트북|맥북|macbook|갤럭시북|그램|씽크패드|비보북|젠북|아이패드|ipad|태블릿|갤럭시탭|스마트폰|아이폰|iphone|갤럭시\s*[SZFlipFold]|"
    r"모니터|키보드|마우스|마우스패드|웹캠|그래픽카드|메인보드|프로세서|CPU|라이젠|인텔|SSD|외장SSD|HDD|외장하드|USB메모리|SD카드|메모리카드|프린터|복합기|스캐너|토너카트리지|잉크카트리지|"
    r"스피커|사운드바|이어폰|헤드폰|헤드셋|에어팟|갤럭시버즈|버즈|마이크|충전기|어댑터|보조배터리|케이블|멀티탭|공유기|라우터|허브|도킹스테이션|거치대|모니터암|카메라|미러리스|액션캠|웹캠|렌즈|삼각대|짐벌|드론|"
    r"텔레비전|스마트TV|빔프로젝터|프로젝터|게임기|플레이스테이션|플스|닌텐도|스위치|엑스박스|컨트롤러|조이스틱|"
    r"커피머신|커피메이커|커피포트|전기포트|무선주전자|에스프레소머신|믹서기|블렌더|착즙기|원액기|커피그라인더|우유거품기|탄산수제조기|"
    r"에어프라이어(?!용)|전자레인지(?!용)|오븐(?!구이|베이크)|가스레인지|인덕션|하이라이트|전기그릴|와플메이커|샌드위치메이커|토스터기|전기밥솥|압력밥솥|밥솥|식기세척기|음식물처리기|정수기|"
    r"냉장고|김치냉장고|냉동고|와인셀러|세탁기|건조기|의류관리기|스타일러|청소기|로봇청소기|무선청소기|침구청소기|물걸레청소기|공기청정기|가습기|제습기|선풍기|서큘레이터|에어컨|히터|온풍기|전기장판|온수매트|전기매트|다리미|스팀다리미|보풀제거기|미싱|재봉틀|"
    r"드라이기|헤어드라이어|고데기|매직기|에어랩|전동칫솔|구강세정기|면도기|전기면도기|제모기|체중계|인바디|혈압계|안마기|마사지기|안마의자|"
    r"주방용품|조리도구|보관용기|밀폐용기|반찬통|도시락통|텀블러|보온병|보냉병|물병|머그컵|유리컵|와인잔|프라이팬|궁중팬|냄비|전골냄비|뚝배기|주전자|도마|식칼|주방가위|채칼|국자|뒤집개|집게|수저|숟가락|젓가락|포크|나이프|식기|접시|그릇|찬기|면기|쟁반|트레이|식기건조대|싱크대|수세미|행주|고무장갑|호일|종이호일|크린랩|지퍼백|"
    r"가구|인테리어|홈데코|수납/정리|서랍장|서랍|수납장|수납함|수납박스|리빙박스|공간박스|트롤리|행거|시스템행거|옷장|붙박이장|신발장|거실장|TV장|장식장|진열장|책장|책상|컴퓨터책상|스탠딩책상|테이블|식탁|접이식식탁|아일랜드식탁|화장대|콘솔|협탁|선반|철제선반|렌지대|파티션|"
    r"의자|사무용의자|게이밍의자|식탁의자|스툴|벤치|소파|리클라이너|빈백|침대|침대프레임|매트리스|토퍼|이불|차렵이불|베개|경추베개|베개커버|매트리스커버|침구|패드|담요|커튼|암막커튼|블라인드|롤스크린|러그|카펫|발매트|주방매트|층간소음매트|벽지|시트지|조명|무드등|스탠드조명|형광등|LED등|전구|액자|시계|벽시계|탁상시계|거울|전신거울|우산|양산|빨래건조대|빨래바구니|옷걸이|바지걸이|휴지통|쓰레기통|분리수거함|"
    r"패션의류|패션잡화|남성의류|여성의류|아동의류|유아동의류|아우터|상의|하의|패딩|숏패딩|롱패딩|경량패딩|자켓|재킷|블레이저|코트|트렌치코트|점퍼|블루종|바람막이|윈드브레이커|플리스|뽀글이|조끼|베스트|가디건|니트|스웨터|맨투맨|스웻셔츠|후드티|후드집업|티셔츠|반팔티|긴팔티|카라티|셔츠|남방|블라우스|"
    r"바지|팬츠|청바지|데님팬츠|슬랙스|면바지|치노팬츠|조거팬츠|카고팬츠|트레이닝바지|트레이닝복|추리닝|반바지|숏팬츠|버뮤다팬츠|레깅스|원피스|스커트|치마|점프수트|정장|수트|한복|잠옷|파자마|홈웨어|수영복|비키니|래쉬가드|속옷|언더웨어|브라|브래지어|팬티|드로즈|트렁크|런닝|내복|발열내의|양말|덧신|스타킹|"
    r"신발|슈즈|운동화|스니커즈|런닝화|러닝화|워킹화|등산화|트레킹화|축구화|풋살화|농구화|배드민턴화|테니스화|골프화|볼링화|안전화|실내화|단화|캔버스화|구두|로퍼|더비슈즈|옥스포드화|부츠|앵클부츠|첼시부츠|레인부츠|장화|털부츠|어그|슬리퍼|샌들|쪼리|클로그|크록스|뮬|플랫슈즈|메리제인|하이힐|펌프스|깔창|신발끈|"
    r"에어포스|에어맥스|나이키\s*덩크|조던|코트비전|줌보메로|뉴발란스\s*\d{3,4}|아디다스\s*(?:삼바|가젤|슈퍼스타|스탠스미스)|컨버스\s*척테일러|반스\s*올드스쿨|아식스\s*젤|살로몬\s*XT|"
    r"가방|백팩|배낭|크로스백|메신저백|숄더백|토트백|에코백|보스턴백|더플백|클러치|파우치|노트북가방|서류가방|캐리어|여행가방|지갑|반지갑|장지갑|카드지갑|명함지갑|벨트|멜빵|모자|볼캡|버킷햇|비니|베레모|선캡|머플러|목도리|스카프|장갑|선글라스|안경테|청광안경|손목시계|스마트워치|애플워치|갤럭시워치|워치스트랩|목걸이|반지|귀걸이|팔찌|발찌|헤어핀|머리끈|브로치|키링|열쇠고리|"
    r"도서|단행본|소설|에세이|시집|만화책|웹툰단행본|수험서|문제집|참고서|기출문제|자격증책|어린이도서|동화책|원서|음반|블루레이|"
    r"문구|오피스|볼펜|만년필|샤프|연필|형광펜|마카|필통|노트|공책|다이어리|플래너|스케줄러|메모지|포스트잇|바인더|화일|클리어파일|복사용지|A4용지|가위|커터칼|스테이플러|테이프|박스테이프|풀|계산기|화이트보드|"
    r"스포츠/레저|자전거|전기자전거|킥보드|텐트|타프|침낭|캠핑의자|캠핑테이블|랜턴|쿨러|아이스박스|등산스틱|배낭|아령|덤벨|케틀벨|바벨|철봉|치닝디핑|실내자전거|런닝머신|스텝퍼|요가매트|폼롤러|라켓|배드민턴|테니스|탁구|골프채|골프공|골프장갑|축구공|농구공|야구글러브|낚싯대|릴|"
    r"완구|장난감|레고|블록|퍼즐|보드게임|피규어|프라모델|인형|봉제인형|미니카|RC카|유모차|카시트|아기띠|보행기|젖병|공갈젖꼭지|"
    r"반려동물|강아지사료|고양이사료|애견간식|고양이간식|배변패드|고양이모래|캣타워|스크래처|목줄|하네스|이동장|수족관|어항|"
    r"자동차용품|블랙박스|하이패스|차량용충전기|차량용거치대|와이퍼|워셔액|불스원샷|카매트|세차용품|타이어|엔진오일|"
    r"공구|전동드릴|드라이버세트|렌치|펜치|망치|줄자|수평계|글루건|납땜|멀티미터|사다리|대차|건전지|배터리(?!\s*맛)|자물쇠|도어락|방충망|문풍지|경첩|나사|못|"
    r"휴대폰케이스|폰케이스|아이폰케이스|갤럭시케이스|에어팟케이스|보호필름|강화유리필름|스마트톡|그립톡|오픈소스|소스코드|아두이노|라즈베리파이"
)

# 페이지 본문/옵션 영역의 강한 일반 상품 보조 신호 (상품명에 품목 단어가 생략된 브랜드 모델명일 때 작동)
_PAGE_GENERAL_SPEC_RE = re.compile(
    r"사이즈\s*선택|색상\s*선택|발볼|굽높이|갑피|밑창|창소재|어깨너비|가슴단면|총장|소매길이|세탁방법|드라이클리닝|"
    r"\b2[2-8][05]\s*mm\b|방문설치|직접설치|가구배송|조립품|자재등급|E0등급|정격전압|소비전력|에너지소비효율|KC\s*인증|전파인증|"
    r"블루투스\s*\d|해상도|주사율|그래픽카드|운영체제"
)
_PAGE_FOOD_SPEC_RE = re.compile(
    r"영양정보|원재료명|총\s*내용량|\b\d{2,4}\s*kcal\b|소비기한|유통기한|냉장보관|냉동보관|실온보관|"
    r"품목보고번호|식품의\s*유형|HACCP|해썹|100\s*g당|100\s*ml당"
)
_PAGE_COSMETIC_SPEC_RE = re.compile(
    r"전성분|화장품법에\s*따라|화장품책임판매업자|화장품제조업자|피부타입|기능성\s*화장품|SPF\s*\d+|PA\+{1,4}"
)

# ==============================================================================
# Phase 2: 성분표 앵커(오타 허용) 및 표(Table) 다음 행 경계·플레이스홀더 패턴
# ==============================================================================
_ANCHOR_PRIMARY_RE = re.compile(
    r"원[재제채체][료로묘](?:명|및|함량|표시|:|：)|"
    r"^원[재제채체][료로묘]$|"
    r"원료(?:명|및함량)|주원료|성분(?:명|및함량|표시)|배합비율|"
    r"전[성정][분본]|모[든튼][성정][분본]|화장품법에따라기재|사용된모든성분|"
    r"알[레래리]르기(?:유발물질|유발성분|물질|정보|표시)"
)
_ANCHOR_SECONDARY_RE = re.compile(r"영양[정성][보분]")

# 2단 상품정보제공고시 표에서 '원재료명' 아래 행(다른 항목 th)을 만나면 성분 수집을 멈추기 위한 패턴
_NEXT_TABLE_ROW_HEADER_RE = re.compile(
    r"^(?:영양[성정][분보]|유전자변형|수입식품|생산자|제조원|유통전문판매원|제조연월일|소비기한|유통기한|품질유지기한|"
    r"포장단위|품목보고|보관방법|섭취량|섭취시주의|소비자안전|소비자상담|"
    r"A/S책임|제조국|원산지|사용기한|사용시주의|사용할때의주의|품질보증|화장품제조|화장품책임|책임판.*업자|기능성화장품)"
)

# '상품 상세설명 참조' 등 실제 성분이 아닌 플레이스홀더 문구
_INGREDIENT_PLACEHOLDER_RE = re.compile(
    r"상품\s*상세\s*(?:설명|페이지|이미지)?\s*참조|상세\s*(?:설명|페이지|이미지|정보|내용)\s*참조|"
    r"하단\s*(?:상세|이미지)?\s*참조|이미지\s*참조|별도\s*표기|패키지\s*참조|용기\s*별도\s*표기|"
    r"해당\s*사항\s*없음|해당\s*없음|"
    r"농수산물의\s*원산지\s*표시에\s*관한\s*법률에\s*따른\s*원산지\s*표시\s*포함|"
    r"원산지\s*표시에\s*관한\s*법률|원산지\s*표시\s*포함|"
    r"화장품법에\s*따라\s*기재해야\s*하는\s*모든\s*성분|화장품법에\s*따라\s*기재|"
    r"식품위생법에\s*따른\s*표시\s*사항|유전자변형식품에\s*해당하는\s*경우|수입식품에\s*해당하는\s*경우"
)


def classify_product_category(
    product_name: Optional[str],
    breadcrumbs: Optional[Sequence[str]] = None,
    page_texts: Optional[Sequence[str]] = None,
) -> str:
    """
    상품명(가중치 3) + 상단 카테고리 경로(Breadcrumb, 가중치 3) + 화면 내 스펙/문맥 신호(가중치 1)를
    종합하여 상품 성격을 4가지로 고정밀 분류합니다.
    - 'food': 식품·건강기능식품 (원재료명/알레르기 성분표 탐색 필요)
    - 'cosmetic': 화장품·피부접촉 생활화학용품 (전성분 탐색 필요)
    - 'general_product': 의류·신발(운동화)·가구(서랍장)·가전·전자·주방도구·문구 등 비성분 일반 상품 (즉시 조기 종료)
    - 'unknown': 판단 근거 부족 (안전 우선으로 성분표 탐색 계속)
    """
    primary_text = " ".join(part for part in [product_name or "", *(breadcrumbs or [])] if part).strip()
    context_text = " ".join(part for part in (page_texts or []) if part).strip()
    combined_all = f"{primary_text} {context_text}".strip()
    if not combined_all:
        return "unknown"

    # [안전 가드] 화면 어디든 원재료명·전성분·영양정보·소비기한·품목보고번호 등이 이미 보이면 절대 일반 상품이 아님!
    has_strict_ing_guard = bool(_STRICT_INGREDIENT_DOMAIN_GUARD_RE.search(combined_all))
    if has_strict_ing_guard:
        if _COSMETIC_CATEGORY_RE.search(primary_text) or _PAGE_COSMETIC_SPEC_RE.search(combined_all):
            return "cosmetic"
        return "food"

    # 가중 점수 합산
    food_score = 0.0
    cosmetic_score = 0.0
    general_score = 0.0

    if primary_text:
        # OCR이 한글 복합어를 띄어 읽은 경우('배드민 턴화' -> '배드민턴화', '서랍 장' -> '서랍장')도 매칭되도록 공백 압축본 병행
        primary_compact = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", primary_text)
        food_hits = len(set(_FOOD_CATEGORY_RE.findall(primary_text)) | set(_FOOD_CATEGORY_RE.findall(primary_compact)))
        cos_hits = len(set(_COSMETIC_CATEGORY_RE.findall(primary_text)) | set(_COSMETIC_CATEGORY_RE.findall(primary_compact)))
        gen_hits = len(set(_GENERAL_PRODUCT_RE.findall(primary_text)) | set(_GENERAL_PRODUCT_RE.findall(primary_compact)))
        food_score += food_hits * 3.5
        cosmetic_score += cos_hits * 3.5
        general_score += gen_hits * 3.5

        # '커피머신', '에어프라이어', '우유거품기', '냉장고', '밥솥', '밀폐용기' 등 식품 단어가 포함된 가전/주방기구 보정
        if re.search(
            r"커피머신|커피메이커|커피포트|에스프레소머신|우유거품기|탄산수제조기|"
            r"에어프라이어(?!용)|전자레인지(?!용)|김치냉장고|냉장고|전기밥솥|압력밥솥|밥솥|"
            r"보관용기|밀폐용기|반찬통|도시락통|텀블러|보온병|프라이팬|냄비|식기|수저|"
            r"강아지사료|고양이사료|애견간식|고양이간식|오픈소스|소스코드",
            primary_text,
        ):
            general_score += 6.0
            food_score = max(0.0, food_score - 4.0)

    if context_text:
        food_score += min(len(_FOOD_CATEGORY_RE.findall(context_text)) * 0.8, 3.2)
        cosmetic_score += min(len(_COSMETIC_CATEGORY_RE.findall(context_text)) * 0.8, 3.2)
        general_score += min(len(_GENERAL_PRODUCT_RE.findall(context_text)) * 0.9, 4.5)

        if _PAGE_FOOD_SPEC_RE.search(context_text):
            food_score += 5.0
        if _PAGE_COSMETIC_SPEC_RE.search(context_text):
            cosmetic_score += 5.0
        if _PAGE_GENERAL_SPEC_RE.search(context_text):
            general_score += 4.0

    best = max(food_score, cosmetic_score, general_score)
    if best < 2.5:
        return "unknown"

    if cosmetic_score >= food_score and cosmetic_score >= general_score and cosmetic_score >= 2.5:
        return "cosmetic"

    if general_score > food_score and general_score > cosmetic_score and general_score >= 3.0:
        return "general_product"

    if food_score >= 2.5:
        return "food"

    return "unknown"


class OCRSingletonEngine:
    """
    [PaddleOCR / Windows Native OCR 싱글톤 패턴]
    워커 프로세스 시작 시(또는 최초 호출 시) 단 1회만 메모리에 로드하여 재사용합니다.
    """

    _instance: Optional["OCRSingletonEngine"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "OCRSingletonEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        with self._lock:
            if getattr(self, "_initialized", False):
                return
            self._ocr_model = None
            self._tls = threading.local()
            self._load_model()
            self._initialized = True

    def _load_model(self) -> None:
        import os
        import sys
        import types

        self._use_windows_native_ocr = False
        self._win_ocr_proc = None
        self._win_ocr_lock = threading.Lock()

        if sys.platform == "win32" and os.getenv("VISION_FORCE_PADDLE", "0") != "1":
            try:
                self._use_windows_native_ocr = True
                self._ocr_model = None
                self._ensure_win_ocr_daemon()
                logger.info(
                    "[OCRSingletonEngine] Windows Native 한국어 OCR 상주 워커(2x 고해상도 보정 모드) 활성화 완료."
                )
                return
            except Exception as win_exc:
                logger.warning(f"[OCRSingletonEngine] Windows Native OCR 데몬 초기화 실패 ({win_exc}), PaddleOCR로 전환합니다.")
                self._use_windows_native_ocr = False

        try:
            try:
                import lmdb  # noqa: F401
            except Exception:
                # 학습 전용 LMDB 모듈이 Windows 정책 등으로 로드되지 않아도 추론이 정상 동작하도록 스텁 등록
                sys.modules.setdefault("lmdb", types.ModuleType("lmdb"))

            from paddleocr import PaddleOCR

            cpu_threads = min(8, os.cpu_count() or 4)
            logger.info(f"[OCRSingletonEngine] PaddleOCR (lang='korean', threads={cpu_threads}) 모델을 메모리에 로드합니다...")
            self._ocr_model = PaddleOCR(
                lang="korean",
                use_angle_cls=False,
                use_gpu=False,
                cpu_threads=cpu_threads,
                det_limit_side_len=settings.OCR_DET_LIMIT_SIDE,
                rec_batch_num=settings.REC_BATCH_NUM,
                show_log=False,
            )
            self._fix_recognition_width(self._ocr_model)
            logger.info("[OCRSingletonEngine] PaddleOCR 싱글톤 로드 완료.")
        except Exception as exc:
            logger.warning(
                f"[OCRSingletonEngine] PaddleOCR 로드 제한 감지 ({exc}). "
                "Windows Native 한국어 OCR 상주 워커로 자동 전환합니다."
            )
            self._ocr_model = None
            self._use_windows_native_ocr = True

    @staticmethod
    def _fix_recognition_width(ocr_model) -> None:
        """
        [메모리 증가 방지 #66] 입력 폭을 REC_WIDTH_RATIOS 중 하나로만 정해 입력 모양 수를 고정한다.
        """
        recognizer = getattr(ocr_model, "text_recognizer", None)
        if recognizer is None or not hasattr(recognizer, "resize_norm_img"):
            logger.warning("[OCRSingletonEngine] 인식기 구조가 예상과 달라 입력 폭을 고정하지 못했습니다.")
            return
        original = recognizer.resize_norm_img
        ratios = sorted(float(x) for x in settings.REC_WIDTH_RATIOS.split(",") if x.strip())

        def fixed_width(img, max_wh_ratio):
            h, w = img.shape[:2]
            own = w / max(h, 1)
            return original(img, next((r for r in ratios if own <= r), ratios[-1]))

        recognizer.resize_norm_img = fixed_width

    @staticmethod
    def _to_fixed_canvas(image: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        [메모리 증가 방지 #66 + 작은 ROI 확대 보정]
        검출 입력을 항상 OCR_CANVAS_WIDTH × OCR_CANVAS_HEIGHT 고정 모양으로 유지하면서,
        작은 성분표 ROI 크롭 이미지(높이 <= 800, 폭 <= 1300)는 동일 캔버스 안에서 최대 1.8배 확대하여
        11~12px 작은 한글 원재료명 인식률을 높인다(캔버스 크기는 고정이라 추가 메모리 증가 0).
        """
        import cv2

        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        canvas_w, canvas_h = settings.OCR_CANVAS_WIDTH, settings.OCR_CANVAS_HEIGHT
        h, w = image.shape[:2]
        max_scale = 1.8 if (h <= 800 and w <= 1350) else 1.0
        scale = min(canvas_w / max(w, 1), canvas_h / max(h, 1), max_scale)
        if abs(scale - 1.0) > 0.05:
            interp = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
            image = cv2.resize(
                image,
                (min(canvas_w, max(1, int(w * scale))), min(canvas_h, max(1, int(h * scale)))),
                interpolation=interp,
            )
        canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
        canvas[: image.shape[0], : image.shape[1]] = image
        return canvas, scale

    def _ensure_win_ocr_daemon(self):
        import subprocess

        if self._win_ocr_proc is not None and self._win_ocr_proc.poll() is None:
            return self._win_ocr_proc

        ps_daemon_script = """
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}
$lang = New-Object Windows.Globalization.Language('ko')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)

while ($null -ne ($imgPath = [Console]::In.ReadLine())) {
    $imgPath = $imgPath.Trim()
    if ([string]::IsNullOrEmpty($imgPath)) { continue }
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imgPath)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $lines = @()
        foreach ($line in $result.Lines) {
            $minX = 999999; $minY = 999999; $maxX = 0; $maxY = 0
            foreach ($word in $line.Words) {
                $r = $word.BoundingRect
                if ($r.X -lt $minX) { $minX = $r.X }
                if ($r.Y -lt $minY) { $minY = $r.Y }
                if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
                if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
            }
            $lines += @{
                text = ($line.Words | ForEach-Object { $_.Text }) -join ''
                text_spaced = $line.Text
                x1 = $minX; y1 = $minY; x2 = $maxX; y2 = $maxY
            }
        }
        $stream.Dispose()
        [Console]::Out.WriteLine((ConvertTo-Json -InputObject @($lines) -Compress))
        [Console]::Out.Flush()
    } catch {
        [Console]::Out.WriteLine("[]")
        [Console]::Out.Flush()
    }
}
"""
        self._win_ocr_proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_daemon_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return self._win_ocr_proc

    def _run_windows_native_ocr(
        self, image: np.ndarray
    ) -> List[Tuple[List[List[float]], str, float]]:
        """
        Windows.Media.Ocr 엔진은 11~13px 웹 한글 폰트(원재료명 표·소형 상품명)를 1x 해상도에서
        누락하거나 오인식('원IH료멍')하는 특성이 있으므로, 저해상도/중해상도 입력을 최대 2.0배
        고화질 보간(INTER_CUBIC) 후 추론하고 좌표를 원본 스케일로 정확히 복원합니다.
        """
        import json
        import os
        import tempfile
        import cv2

        h, w = image.shape[:2]
        scale = min(2.0, 2560.0 / max(w, 1), 3200.0 / max(h, 1))
        if scale > 1.12:
            work_img = cv2.resize(
                image,
                (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                interpolation=cv2.INTER_CUBIC,
            )
        else:
            scale = 1.0
            work_img = image

        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            cv2.imwrite(tmp_path, work_img)
            if work_img is not image:
                del work_img
            with self._win_ocr_lock:
                proc = self._ensure_win_ocr_daemon()
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(tmp_path + "\n")
                proc.stdin.flush()
                stdout_str = proc.stdout.readline().strip()

            if not stdout_str:
                return []

            raw_lines = json.loads(stdout_str)
            if isinstance(raw_lines, dict):
                raw_lines = [raw_lines]

            parsed_items: List[Tuple[List[List[float]], str, float]] = []
            for item in raw_lines:
                if not item:
                    continue
                x1 = float(item.get("x1", 0)) / scale
                y1 = float(item.get("y1", 0)) / scale
                x2 = float(item.get("x2", 0)) / scale
                y2 = float(item.get("y2", 0)) / scale
                box = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                text = str(item.get("text_spaced") or item.get("text") or "").strip()
                if text:
                    parsed_items.append((box, text, 0.95))
            return parsed_items
        except Exception as exc:
            logger.error(f"[WindowsNativeOCR] 추론 오류: {exc}")
            return []
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def run_ocr(self, image: np.ndarray) -> List[Tuple[List[List[float]], str, float]]:
        """
        OCR을 실행하고 결과를 표준화된 리스트 [(box_points, text, confidence), ...] 로 반환합니다.
        """
        if getattr(self, "_use_windows_native_ocr", False):
            return self._run_windows_native_ocr(image)

        if self._ocr_model is None:
            self._load_model()
            if getattr(self, "_use_windows_native_ocr", False):
                return self._run_windows_native_ocr(image)
            if self._ocr_model is None:
                return []

        canvas, scale = self._to_fixed_canvas(image)
        raw_result: Any = self._ocr_model.ocr(canvas, cls=False)
        del canvas
        parsed_items: List[Tuple[List[List[float]], str, float]] = []

        if not raw_result:
            return parsed_items

        lines = raw_result[0] if isinstance(raw_result, list) and len(raw_result) > 0 else []
        if not lines:
            return parsed_items

        for line in lines:
            if not line or len(line) < 2:
                continue
            box = [[float(x) / scale, float(y) / scale] for x, y in line[0]]
            text_info = line[1]
            if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                text = str(text_info[0]).strip()
                score = float(text_info[1])
                if text:
                    parsed_items.append((box, text, score))

        return parsed_items

    @staticmethod
    def calculate_bbox_area(box: List[List[float]]) -> float:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        return float(max(0.0, width) * max(0.0, height))

    @staticmethod
    def _merge_horizontal_line_items(parsed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        같은 줄에서 살짝 떨어진 채 분리된 조각(예: '[단독]' + '나이키 에어포스 1', '109,000' + '원')을
        하나의 줄로 병합합니다. (2단 표의 좌/우 열처럼 간격이 넓은 경우는 병합하지 않음)
        """
        if len(parsed) <= 1:
            return parsed
        ordered = sorted(parsed, key=lambda it: (it["cy"], it["x1"]))
        used = [False] * len(ordered)
        merged_out: List[Dict[str, Any]] = []

        for i, base in enumerate(ordered):
            if used[i]:
                continue
            cur = dict(base)
            used[i] = True
            changed = True
            while changed:
                changed = False
                for j in range(len(ordered)):
                    if used[j]:
                        continue
                    nxt = ordered[j]
                    overlap_y = min(cur["y2"], nxt["y2"]) - max(cur["y1"], nxt["y1"])
                    min_h = max(1.0, min(cur["h"], nxt["h"]))
                    max_h = max(cur["h"], nxt["h"])
                    if overlap_y < 0.58 * min_h or (max_h / min_h) > 1.85:
                        continue
                    avg_h = (cur["h"] + nxt["h"]) * 0.5
                    max_x_gap = max(16.0, avg_h * 1.45)
                    # cur 오른쪽에 nxt가 바로 이어지는 경우
                    if -6.0 <= (nxt["x1"] - cur["x2"]) <= max_x_gap:
                        cur["text"] = f"{cur['text']} {nxt['text']}".strip()
                    elif -6.0 <= (cur["x1"] - nxt["x2"]) <= max_x_gap:
                        cur["text"] = f"{nxt['text']} {cur['text']}".strip()
                    else:
                        continue
                    cur["x1"] = min(cur["x1"], nxt["x1"])
                    cur["y1"] = min(cur["y1"], nxt["y1"])
                    cur["x2"] = max(cur["x2"], nxt["x2"])
                    cur["y2"] = max(cur["y2"], nxt["y2"])
                    cur["w"] = cur["x2"] - cur["x1"]
                    cur["h"] = cur["y2"] - cur["y1"]
                    cur["cx"] = (cur["x1"] + cur["x2"]) * 0.5
                    cur["cy"] = (cur["y1"] + cur["y2"]) * 0.5
                    cur["area"] = cur["w"] * cur["h"]
                    cur["score"] = max(cur["score"], nxt["score"])
                    used[j] = True
                    changed = True
            merged_out.append(cur)

        merged_out.sort(key=lambda it: (it["y1"], it["x1"]))
        return merged_out

    def extract_product_title_and_category(
        self,
        ocr_items: List[Tuple[List[List[float]], str, float]],
        img_width: int,
        img_height: int,
    ) -> Tuple[Optional[str], str, List[str]]:
        """
        [Phase 1: 전 쇼핑몰 호환 레이아웃 삼각측량 기반 상품명 추출 & 다중 신호 카테고리 분류]
        쿠팡뿐 아니라 네이버 스마트스토어, 11번가, G마켓, 옥션, SSG, 마켓컬리, 올리브영, 무신사,
        오늘의집, 29CM, 다나와(상단 전체폭 제목), 반응형 반화면(1단 레이아웃)을 모두 지원합니다.
        """
        if not ocr_items:
            return None, "unknown", []

        W = max(float(img_width), 1.0)
        H = max(float(img_height), 1.0)

        raw_parsed: List[Dict[str, Any]] = []
        for box, raw_text, score in ocr_items:
            text = raw_text.strip()
            if score < 0.45 or len(text) < 1:
                continue
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            x1, x2 = float(min(xs)), float(max(xs))
            y1, y2 = float(min(ys)), float(max(ys))
            w, h = max(1.0, x2 - x1), max(1.0, y2 - y1)
            raw_parsed.append(
                {
                    "text": text,
                    "score": float(score),
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "w": w, "h": h,
                    "cx": (x1 + x2) * 0.5,
                    "cy": (y1 + y2) * 0.5,
                    "area": w * h,
                }
            )

        parsed = [it for it in self._merge_horizontal_line_items(raw_parsed) if len(it["text"]) >= 2]
        if not parsed:
            return None, "unknown", []

        heights = sorted(it["h"] for it in parsed)
        median_h = heights[len(heights) // 2] if heights else 16.0

        breadcrumbs: List[str] = []
        page_context_lines: List[str] = []
        main_prices: List[Dict[str, Any]] = []
        review_anchors: List[Dict[str, Any]] = []
        buy_buttons: List[Dict[str, Any]] = []

        # 우측 끝 크롬 사이드패널(꿀픽 등) 제외 기준선: 넓은 데스크톱 창에서 x1 > 0.80*W
        sidebar_x = 0.80 * W if W >= 960 else 0.96 * W

        for it in parsed:
            txt = it["text"]
            if it["x1"] <= sidebar_x and it["y1"] <= 0.85 * H:
                page_context_lines.append(txt)

            if _BREADCRUMB_RE.search(txt) and it["y1"] < 0.36 * H and it["x1"] <= sidebar_x:
                breadcrumbs.append(txt)

            if it["y1"] < 0.11 * H or it["x1"] > sidebar_x:
                continue

            if _BUY_BUTTON_RE.search(txt):
                buy_buttons.append(it)
            if _MAIN_PRICE_RE.search(txt) and not _SECONDARY_PRICE_NOISE_RE.search(txt):
                main_prices.append(it)
            if _REVIEW_ANCHOR_RE.search(txt):
                review_anchors.append(it)

        # [Buy-Box 삼각측량]
        # 1) 구매/장바구니 버튼이나 메인 가격을 기준으로 실제 구매 컬럼(buy_x1) 결정
        #    - 일반 데스크톱 2단 쇼핑몰(쿠팡/스마트스토어/오늘의집/컬리/올리브영/무신사): x1 = 0.30~0.76*W
        #    - 반응형 좁은 창/모바일 레이아웃: x1 = 0.02~0.35*W
        def _select_primary_price() -> Optional[Dict[str, Any]]:
            if not main_prices:
                return None
            # 구매 버튼이 있으면 구매 버튼 위쪽(y1 < buy_y + 40) & 같은 컬럼의 가격을 최우선 선택
            if buy_buttons:
                btn = min(buy_buttons, key=lambda b: b["y1"])
                aligned = [
                    p for p in main_prices
                    if p["y1"] <= btn["y2"] + 30.0 and abs(p["x1"] - btn["x1"]) <= 0.25 * W
                ]
                if aligned:
                    # 폰트 크기가 크고 상단에 있는 대표 판매가 선택
                    return max(aligned, key=lambda p: (p["h"] * 1.6 - (p["y1"] / H) * 20.0))

            right_col = [p for p in main_prices if 0.28 * W <= p["x1"] <= 0.78 * W and p["y1"] <= 0.72 * H]
            pool = right_col or [p for p in main_prices if p["y1"] <= 0.75 * H] or main_prices
            return max(pool, key=lambda p: (p["h"] * 1.5 - (p["y1"] / H) * 22.0))

        price_ref = _select_primary_price()

        # 리뷰/원산지 앵커는 메인 가격보다 위(또는 같은 컬럼 상단)에 있을 때만 제목 하단 경계로 채택
        # (스마트스토어처럼 하단 탭바에 '리뷰 1,234'가 있는 경우 제목 경계를 망치지 않도록 방어)
        ref: Optional[Dict[str, Any]] = price_ref
        if review_anchors:
            if price_ref is not None:
                upper_reviews = [
                    r for r in review_anchors
                    if abs(r["x1"] - price_ref["x1"]) <= 0.16 * W
                    and (price_ref["y1"] - 0.28 * H) <= r["y1"] <= price_ref["y1"] + 10.0
                ]
                if upper_reviews:
                    ref = min(upper_reviews, key=lambda r: r["y1"])
            else:
                right_rev = [r for r in review_anchors if 0.28 * W <= r["x1"] <= 0.78 * W and r["y1"] <= 0.65 * H]
                pool_rev = right_rev or [r for r in review_anchors if r["y1"] <= 0.65 * H]
                if pool_rev:
                    ref = min(pool_rev, key=lambda r: r["y1"])

        if ref is None and buy_buttons:
            ref = min(buy_buttons, key=lambda b: b["y1"])

        candidates: List[Tuple[float, Dict[str, Any]]] = []
        for it in parsed:
            txt = it["text"]
            if it is ref or it is price_ref:
                continue
            if _BREADCRUMB_RE.search(txt):
                continue
            if _REVIEW_ANCHOR_RE.search(txt) or (_MAIN_PRICE_RE.search(txt) and len(txt) < 28):
                continue
            if _NON_TITLE_LINE_RE.search(txt):
                continue
            if not re.search(r"[가-힣A-Za-z]{2,}", txt):
                continue

            pts = 0.0
            if it["x1"] > sidebar_x:
                pts -= 130.0

            if ref is not None:
                same_col = (
                    abs(it["x1"] - ref["x1"]) <= 0.15 * W
                    or (ref["x1"] - 0.06 * W <= it["x1"] <= ref["x2"] + 0.10 * W and it["x1"] <= sidebar_x)
                )
                # 다나와/가격비교처럼 사진+가격표 위쪽 상단 전체폭에 상품명이 배치된 레이아웃인지 확인
                is_top_spanning_header = (
                    it["y2"] <= ref["y1"] - 0.025 * H
                    and 0.11 * H <= it["y1"] <= 0.34 * H
                    and it["x1"] <= 0.32 * W
                    and it["w"] >= 0.22 * W
                    and it["h"] >= 1.05 * median_h
                )

                if same_col and it["y2"] <= ref["y1"] + max(14.0, 0.025 * H):
                    dy_ratio = max(0.0, ref["y1"] - it["y2"]) / H
                    if dy_ratio <= 0.32:
                        pts += 135.0 - dy_ratio * 210.0
                    elif dy_ratio <= 0.50:
                        pts += 68.0 - (dy_ratio - 0.32) * 180.0
                elif is_top_spanning_header:
                    pts += 82.0
                elif it["x2"] < ref["x1"] - 0.03 * W:
                    # 앵커 왼쪽 상품 갤러리 사진 내부 텍스트 감점
                    pts -= 80.0
                elif price_ref is not None and it["y1"] > price_ref["y2"] + max(14.0, 0.025 * H):
                    # 메인 판매가보다 아래는 배송·옵션 영역
                    pts -= 55.0
                elif it["y1"] > ref["y2"] + max(16.0, 0.03 * H):
                    pts -= 45.0
            else:
                # 가격/리뷰/구매버튼 앵커가 전혀 없는 화면: 상단~중단 제목 크기·길이 중심 평가
                if 0.12 * H <= it["cy"] <= 0.55 * H:
                    pts += 35.0
                pts += min(it["area"] / 900.0, 40.0)

            # 최상단 브라우저 탭·주소창·쇼핑몰 GNB 감점
            if H >= 380 and it["cy"] < 0.11 * H:
                pts -= 70.0
            elif 0.12 * H <= it["cy"] <= 0.65 * H and it["x1"] <= sidebar_x:
                pts += 18.0

            # 텍스트 길이 & 한글/영문 구성 점수 (짧은 단독 브랜드명 '한샘', '나이키'보다 본 상품명 우대)
            if re.search(r"[가-힣]", txt):
                pts += 15.0
            tlen = len(txt)
            if 12 <= tlen <= 95:
                pts += 34.0
            elif 7 <= tlen < 12:
                pts += 18.0
            elif tlen <= 4:
                pts -= 16.0

            # 폰트 높이 비율 점수 (본문보다 약간 크고 굵은 제목 폰트 우대, 사진 속 초대형 배너 글씨 감점)
            rel_h = it["h"] / max(median_h, 8.0)
            h_ratio = it["h"] / H
            if H >= 400 and h_ratio > 0.10 and tlen <= 12:
                pts -= 42.0
            elif 1.05 <= rel_h <= 2.6:
                pts += 22.0
            elif 0.82 <= rel_h < 1.05:
                pts += 10.0
            elif rel_h < 0.72:
                pts -= 12.0

            candidates.append((pts, it))

        if not candidates:
            best_raw = max(parsed, key=lambda it: it["area"])
            title = best_raw["text"]
            cat = classify_product_category(title, breadcrumbs, page_context_lines)
            return title, cat, breadcrumbs

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        best = candidates[0][1]

        # 다중 줄(2~3줄)로 줄바꿈된 상품명 자동 병합 (같은 X 시작점·유사 폰트 높이·바로 인접한 줄)
        merged = [best]
        for _, other in candidates[1:]:
            if other is best or len(other["text"]) < 3:
                continue
            if abs(other["x1"] - best["x1"]) > max(38.0, 0.055 * W):
                continue
            h_ratio_pair = other["h"] / max(best["h"], 1.0)
            if not (0.72 <= h_ratio_pair <= 1.35):
                continue
            top_y = min(m["y1"] for m in merged)
            bot_y = max(m["y2"] for m in merged)
            max_gap = max(12.0, best["h"] * 1.45)
            if (0.0 <= top_y - other["y2"] <= max_gap) or (0.0 <= other["y1"] - bot_y <= max_gap):
                bound_y = ref["y1"] + max(12.0, 0.02 * H) if ref is not None else H
                if other["y2"] <= bound_y:
                    merged.append(other)
                    if len(merged) >= 3:
                        break

        # 만약 바로 위에 짧은 브랜드명(예: '한샘', '나이키', '라운드랩')이 붙어 있으면 앞에 결합해 품목/브랜드 문맥 보존
        top_line = min(merged, key=lambda m: m["y1"])
        for _, other in candidates[1:]:
            if other in merged:
                continue
            otxt = other["text"].strip(" []()>›")
            if 2 <= len(otxt) <= 12 and abs(other["x1"] - top_line["x1"]) <= max(32.0, 0.04 * W):
                gap_up = top_line["y1"] - other["y2"]
                if 0.0 <= gap_up <= max(14.0, top_line["h"] * 1.3) and otxt not in top_line["text"]:
                    merged.append(other)
                    break

        merged.sort(key=lambda m: m["y1"])
        title = " ".join(m["text"] for m in merged)
        # 같은 줄 오른쪽에 붙은 네이버 스마트스토어 별점('* 4.93 (최근 6개월 ...)') 꼬리 제거
        title = re.sub(r"\s*[*★☆]\s*[0-5]\.\d.*$", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        # OCR 중량 오인식 '4009' -> '400g' 보정 (단 연도 2019/2029 및 모델번호 제외)
        title = re.sub(r"(?<!\d)(\d{2,3})9(?=\s*(?:[x×*,]|개|봉|팩|입|$))", r"\1g", title)

        category = classify_product_category(title, breadcrumbs, page_context_lines)
        return title, category, breadcrumbs

    def extract_largest_text_as_product_name(self, first_frame_image: np.ndarray) -> Optional[str]:
        """하위 호환용 래퍼: 개선된 레이아웃 기반 상품명 추출기를 호출합니다."""
        ocr_items = self.run_ocr(first_frame_image)
        if not ocr_items:
            return None
        h, w = first_frame_image.shape[:2]
        title, _, _ = self.extract_product_title_and_category(ocr_items, img_width=w, img_height=h)
        return title

    @staticmethod
    def is_ingredient_anchor(text: str) -> int:
        """
        성분표 앵커 매칭 여부를 우선순위 점수로 반환합니다.
        - 2: 핵심 성분 앵커 ('원재료명', '원재료 및 함량', '전성분', '모든 성분', '알레르기 유발물질' 및 OCR 1글자 오타 포함)
        - 1: 보조 앵커 ('영양정보', '영양성분')
        - 0: 매칭 안 됨
        """
        norm = re.sub(r"[\s·•:：()\[\]\-_]+", "", text or "")
        if not norm:
            return 0
        if _ANCHOR_PRIMARY_RE.search(norm):
            return 2
        for kw in settings.ANCHOR_KEYWORDS:
            kw_norm = kw.replace(" ", "")
            if kw_norm and kw_norm not in ("영양정보", "영양성분") and kw_norm in norm:
                return 2
        if _ANCHOR_SECONDARY_RE.search(norm):
            return 1
        return 0

    def _collect_table_aware_roi_text(
        self,
        ocr_items: List[Tuple[List[List[float]], str, float]],
        anchor_box: List[List[float]],
        tile_width: int,
    ) -> str:
        """
        [2단 상품정보제공고시 표(Table) 대응 수집기]
        1) HTML `<th>원재료명 및 함량</th>`이 세로 중앙 정렬(`vertical-align: middle`)되어 있을 때
           오른쪽 `<td>`의 첫 줄들이 `anchor_y`보다 최대 `ROI_TOP_PADDING(160px)` 위에 위치하는 문제를 해결합니다.
        2) 좌측 헤더 컬럼(`anchor_x2 < 0.45 * W`)에서 `anchor_y` 아래에 새로운 다른 항목 헤더
           ('생산자 및 소재지', '소비기한', '수입식품...' 등)가 등장하면 그 Y좌표에서 즉시 수집을 멈춰
           엉뚱한 다음 행 텍스트가 섞이지 않게 차단합니다.
        """
        ax1 = min(pt[0] for pt in anchor_box)
        ax2 = max(pt[0] for pt in anchor_box)
        ay1 = min(pt[1] for pt in anchor_box)
        ay2 = max(pt[1] for pt in anchor_box)

        roi_top = ay1 - settings.ROI_TOP_PADDING
        roi_bottom = ay1 + settings.ROI_CROP_HEIGHT
        is_left_th = ax2 < 0.46 * max(tile_width, 1)

        # 다음 행(th) 시작 Y좌표 탐지하여 하단 경계(stop_y) 정밀 제한
        stop_y = roi_bottom
        if is_left_th:
            for box, text, score in ocr_items:
                if score < 0.45:
                    continue
                bx1 = min(pt[0] for pt in box)
                by1 = min(pt[1] for pt in box)
                if by1 <= ay2 + 12.0 or by1 >= stop_y:
                    continue
                if abs(bx1 - ax1) <= max(60.0, 0.08 * tile_width):
                    norm_t = re.sub(r"[\s·•:：()\[\]]+", "", text)
                    if _NEXT_TABLE_ROW_HEADER_RE.search(norm_t):
                        stop_y = min(stop_y, by1 - 4.0)

        collected: List[Tuple[float, float, str]] = []
        for box, text, score in ocr_items:
            if score < 0.45:
                continue
            bx1 = min(pt[0] for pt in box)
            by1 = min(pt[1] for pt in box)
            by2 = max(pt[1] for pt in box)

            # 앵커보다 위쪽(ay1 이전) 텍스트는 2단 표의 우측 셀(bx1 >= ax2 - 15)일 때만 포함!
            # (단일 컬럼 상세 이미지에서 앵커 바로 위의 일반 홍보 문구가 딸려오는 것을 방지)
            if by2 < ay1 - 4.0:
                if not (is_left_th and by1 >= roi_top and bx1 >= ax2 - 15.0):
                    continue
            elif by1 > stop_y:
                continue

            collected.append((by1, bx1, text))

        collected.sort(key=lambda t: (round(t[0] / 10.0), t[1]))
        return "\n".join(t[2] for t in collected)

    def find_all_anchors_and_initial_ingredients(
        self,
        tiles: List[Tuple[int, np.ndarray]],
        precomputed_first_tile: Optional[List[Tuple[List[List[float]], str, float]]] = None,
    ) -> Tuple[List[int], List[str]]:
        """
        [다중 앵커 탐색 + '상세설명 참조' 자동 우회]
        한 화면 안에 상단 요약표('원재료명 | 상세설명 참조')와 실제 하단 성분표가 동시에 있을 때,
        첫 번째 빈 앵커에서 멈추지 않고 프레임 내 모든 앵커 후보를 검사하여 실제 성분을 찾아냅니다.
        """
        anchor_hits: List[Tuple[int, int, List[List[float]], List[Tuple[List[List[float]], str, float]], int]] = []
        all_frame_texts: List[str] = []
        tile0_items_saved: List[Tuple[List[List[float]], str, float]] = []
        tile0_shape: Tuple[int, int] = (0, 0)

        for idx, (y_offset, tile_img) in enumerate(tiles):
            ocr_items = (
                precomputed_first_tile
                if (idx == 0 and precomputed_first_tile is not None)
                else self.run_ocr(tile_img)
            )
            if idx == 0:
                tile0_items_saved = ocr_items
                tile0_shape = (tile_img.shape[1], tile_img.shape[0])
            for _, t_str, sc in ocr_items:
                if sc >= 0.45 and t_str:
                    all_frame_texts.append(t_str)
            tile_w = tile_img.shape[1]
            for box, text, _ in ocr_items:
                prio = self.is_ingredient_anchor(text)
                if prio > 0:
                    min_y_in_tile = min(pt[1] for pt in box)
                    global_anchor_y = int(y_offset + min_y_in_tile)
                    # 중복 타일 오버랩 구간의 동일 앵커 중복 제거
                    if any(abs(global_anchor_y - prev[1]) <= 28 for prev in anchor_hits):
                        continue
                    logger.info(
                        f"[Anchor Found] prio={prio}, 텍스트='{text}', Global Y={global_anchor_y}px"
                    )
                    anchor_hits.append((prio, global_anchor_y, box, ocr_items, tile_w))

        tls = getattr(self, "_tls", None)
        if tls is not None:
            tls.last_scan_info = {
                "tile0_items": tile0_items_saved,
                "tile0_size": tile0_shape,
                "all_texts": all_frame_texts,
            }

        if not anchor_hits:
            return [], []

        # 핵심 성분 앵커(prio=2: 원재료명/전성분/모든성분/알레르기)를 보조 앵커(prio=1: 영양정보)보다 먼저 평가
        anchor_hits.sort(key=lambda h: (-h[0], h[1]))

        ordered_ys: List[int] = [h[1] for h in anchor_hits]
        for _prio, _gy, box, ocr_items, tile_w in anchor_hits:
            raw_roi_text = self._collect_table_aware_roi_text(ocr_items, box, tile_w)
            fast_ingredients = self.clean_ingredient_text(raw_roi_text)
            if len(fast_ingredients) >= 2:
                return ordered_ys, fast_ingredients

        return ordered_ys, []

    def find_anchor_and_initial_ingredients(
        self,
        tiles: List[Tuple[int, np.ndarray]],
        anchor_keywords: List[str] = settings.ANCHOR_KEYWORDS,
    ) -> Tuple[Optional[int], List[str]]:
        anchor_ys, fast_ingredients = self.find_all_anchors_and_initial_ingredients(tiles)
        return (anchor_ys[0] if anchor_ys else None), fast_ingredients

    def find_anchor_y_coordinate(
        self,
        tiles: List[Tuple[int, np.ndarray]],
        anchor_keywords: List[str] = settings.ANCHOR_KEYWORDS,
    ) -> Optional[int]:
        anchor_y, _ = self.find_anchor_and_initial_ingredients(tiles, anchor_keywords)
        return anchor_y

    def extract_and_clean_ingredients(self, enhanced_roi: np.ndarray) -> List[str]:
        """
        CLAHE 및 샤프닝 전처리가 완료된 ROI 이미지에서 표 경계를 고려해 텍스트를 추출하고 정제합니다.
        """
        ocr_items = self.run_ocr(enhanced_roi)
        if not ocr_items:
            return []

        tile_w = enhanced_roi.shape[1]
        # ROI 내부에서 핵심 앵커 위치를 다시 잡아 2단 표 경계 필터링 적용
        best_box = None
        best_prio = 0
        for box, text, score in ocr_items:
            if score < 0.45:
                continue
            p = self.is_ingredient_anchor(text)
            if p > best_prio:
                best_prio = p
                best_box = box

        if best_box is not None:
            combined_text = self._collect_table_aware_roi_text(ocr_items, best_box, tile_w)
        else:
            ocr_items.sort(key=lambda item: (round(min(pt[1] for pt in item[0]) / 10.0), min(pt[0] for pt in item[0])))
            combined_text = "\n".join(text for _, text, score in ocr_items if score >= 0.45)

        return self.clean_ingredient_text(combined_text)

    @staticmethod
    def clean_ingredient_text(raw_text: str) -> List[str]:
        """
        정규표현식(Regex) + 한국어 OCR 오타 보정 기반 성분 텍스트 정제 파이프라인:
        1. '상세설명 참조'·법령 안내문·타 행 헤더 제거
        2. 한국어 소형 폰트 대표 OCR 오타 보정 ('일가루' -> '밀가루', '대두, 일' -> '대두, 밀', '나트름' -> '나트륨' 등)
        3. 괄호 안 알레르기 핵심 원료 보존 및 원산지·퍼센트 수치 제거
        4. 중복 없는 성분 리스트(List[str]) 반환
        """
        if not raw_text or not raw_text.strip():
            return []

        text = raw_text

        # 0. 플레이스홀더('상세설명 참조' 등) 및 법령 상투어 선제 제거
        text = _INGREDIENT_PLACEHOLDER_RE.sub(",", text)

        # 1. 앵커 헤더 문구 제거 (오타 변형 포함)
        header_pattern = (
            r"(?:원[재제채체][료로묘]명\s*및\s*함량|원[재제채체][료로묘]\s*및\s*함량|원[재제채체][료로묘]명|원[재제채체][료로묘]|"
            r"원료명\s*및\s*함량|원료\s*및\s*함량|성분명\s*및\s*함량|성분\s*및\s*함량|주원료명|"
            r"영양정보|영양성분|전[성정][분본]|모[든튼]\s*[성정][분본]|성분명|원료명|배합비율|및\s*함량)\s*[:：]?"
        )
        text = re.sub(header_pattern, ",", text)

        # 1-1. 한국어 OCR 닫는 괄호 오타 '), ' -> '기 ' 보정 및 대표 원료 오인식 복원
        text = re.sub(r"\(([^(),]{1,25}?)기(?=\s|,|$)", r"(\1),", text)
        text = re.sub(r"([가-힣]{2,10}(?:산|우유|대두|밀|계란|땅콩))기(?=\s|,|$)", r"(\1),", text)
        text = text.replace("일가루", "밀가루").replace("우리일", "우리밀").replace("통일가루", "통밀가루")
        text = text.replace("나트름", "나트륨").replace("칼름", "칼륨").replace("칼숨", "칼슘")
        text = text.replace("마틀", "마늘").replace("도H지고기", "돼지고기")

        # 2. 괄호 안을 지우지 않고 쉼표로 펼쳐 '(밀:미국산)'·'(우유, 대두)' 내부 알레르기 원료 보존 (#62)
        text = re.sub(r"[()\[\]{}]", ",", text)

        # 3. 함량 퍼센트·중량 수치 제거 ('%'는 비단어 문자이므로 \b를 뒤에 붙이지 않음!)
        text = re.sub(r"\d+(?:\.\d+)?\s*(?:%|(?:kcal|mg|g|kg|ml|l)\b)", "", text, flags=re.IGNORECASE)

        # 4. L•글루탐산나트륨 -> L-글루탐산나트륨 선제 복원 후 구분자 통일
        text = re.sub(r"([A-Za-z])\s*[•·]\s*(?=[가-힣])", r"\1-", text)
        text = re.sub(r"[\n\r•·;:/|]+", ",", text)
        text = re.sub(r"\.(?=\s|$)", ",", text)
        text = re.sub(r"(?<=[가-힣])\s+(?=[A-Za-z]\s*[-•])", ",", text)

        # 5. 특수문자 정리
        text = re.sub(r"[^가-힣a-zA-Z0-9,\-\s]", " ", text)

        stopwords = {
            "함유", "포함", "함량", "원재료", "원재료명", "전성분", "모든성분", "외", "기타", "기준", "일일영양성분", "영양성분",
            "기준치에대한비율", "총내용량", "내용량",
            "나트륨", "탄수화물", "당류", "식이섬유", "지방", "트랜스지방", "포화지방", "콜레스테롤", "단백질", "열량",
            "미국산", "호주산", "국내산", "국산", "중국산", "독일산", "말레이시아산", "인도네시아산", "베트남산", "태국산",
            "캐나다산", "브라질산", "스페인산", "이탈리아산", "프랑스산", "칠레산", "페루산", "아르헨티나산", "러시아산", "노르웨이산",
            "외국산", "수입산", "별도표기", "상세참조", "상세설명참조", "상품상세참조", "원산지", "제조원", "유통전문판매원",
            "생산자및소재지", "소비자상담", "품목보고번호", "소비기한", "유통기한", "보관방법", "주식회사",
        }

        cleaned_ingredients: List[str] = []
        seen = set()

        for token in text.split(","):
            item = re.sub(r"\s+", " ", token).strip(" -_.")
            item = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", item)
            if not item:
                continue

            # Windows OCR이 단독 알레르기 원료 '밀'을 '일'로 오인식한 토큰('대두, 일, 돼지고기') 정확히 복원
            if item == "일":
                item = "밀"

            if item.isdigit() or (len(item) < 2 and item not in ALLERGEN_SINGLE_CHARS):
                continue

            if len(item) > 80:
                # 80자를 넘는 장문 일반 문단은 성분명이 아님 (교차오염 알레르기 안내문 30~70자는 보존)
                continue

            if _NEXT_TABLE_ROW_HEADER_RE.search(item) or _INGREDIENT_PLACEHOLDER_RE.search(item):
                continue

            if item in stopwords or (item.endswith("산") and len(item) <= 4 and item not in ACID_INGREDIENTS):
                continue

            if "소비자" in item or "전화번호" in item or "교환" in item or "보상" in item:
                continue

            item = re.sub(r"알[레래리]르기\s*(?:유발\s*(?:물질|성분)|정보|표시)?|유발\s*(?:물질|성분)", "", item).strip(" -_.")
            if item == "일":
                item = "밀"
            elif item == "일함유":
                item = "밀함유"
            if not item or (len(item) < 2 and item not in ALLERGEN_SINGLE_CHARS):
                continue
            if item in stopwords:
                continue

            if item not in seen:
                seen.add(item)
                cleaned_ingredients.append(item)

        return cleaned_ingredients


def get_ocr_engine() -> OCRSingletonEngine:
    return OCRSingletonEngine()
