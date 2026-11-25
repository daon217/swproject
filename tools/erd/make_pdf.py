"""꿀픽 maintest 프로젝트 정리 PDF (run in kkulpick-docgen container: /d = erd dir, /o = output dir)."""
import sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

D, O = Path(sys.argv[1]), Path(sys.argv[2])
NANUM = "/usr/share/fonts/truetype/nanum/"
pdfmetrics.registerFont(TTFont("KR", NANUM + "NanumGothic.ttf"))
pdfmetrics.registerFont(TTFont("KRB", NANUM + "NanumGothicBold.ttf"))
pdfmetrics.registerFontFamily("KR", normal="KR", bold="KRB", italic="KR", boldItalic="KRB")

INK, MUTED, ACCENT, LINE, SOFT = (colors.HexColor(c) for c in ("#0f172a", "#64748b", "#1d4ed8", "#cbd5e1", "#f1f5f9"))
S = {
    "title": ParagraphStyle("title", fontName="KRB", fontSize=26, leading=34, textColor=INK, alignment=TA_CENTER),
    "sub": ParagraphStyle("sub", fontName="KR", fontSize=12, leading=18, textColor=MUTED, alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", fontName="KRB", fontSize=17, leading=24, textColor=ACCENT, spaceBefore=4, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="KRB", fontSize=12.5, leading=18, textColor=INK, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="KR", fontSize=9.5, leading=15, textColor=INK, spaceAfter=4),
    "bullet": ParagraphStyle("bullet", fontName="KR", fontSize=9.5, leading=14.5, textColor=INK, leftIndent=12,
                             bulletIndent=2, spaceAfter=1.5),
    "cell": ParagraphStyle("cell", fontName="KR", fontSize=8.3, leading=11.5, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="KRB", fontSize=8.3, leading=11.5, textColor=colors.white),
    "note": ParagraphStyle("note", fontName="KR", fontSize=8.3, leading=12, textColor=MUTED),
}


def P(t, s="body"): return Paragraph(t, S[s])
def H1(t): return P(t, "h1")
def H2(t): return P(t, "h2")
def B(items): return [Paragraph(i, S["bullet"], bulletText="•") for i in items]
def code(t): return f'<font name="KRB" color="#334155">{t}</font>'


def T(rows, widths, head=True, zebra=True):
    data = [[Paragraph(str(c), S["cellb" if head and i == 0 else "cell"]) for c in r] for i, r in enumerate(rows)]
    st = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT))
    if zebra:
        st += [("BACKGROUND", (0, i), (-1, i), SOFT) for i in range(2 if head else 1, len(rows), 2)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    t.setStyle(TableStyle(st))
    return t


W, H = A4
M = 16 * mm


def deco(canvas, doc):
    canvas.saveState()
    canvas.setFont("KR", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(M, 9 * mm, "꿀픽(KkulPick) · maintest d0a46f8 기준 · 2026-11-25")
    canvas.drawRightString(W - M, 9 * mm, f"{doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(M, 12 * mm, W - M, 12 * mm)
    canvas.restoreState()


doc = BaseDocTemplate(str(O / "꿀픽_maintest_프로젝트_정리.pdf"), pagesize=A4, leftMargin=M, rightMargin=M,
                      topMargin=15 * mm, bottomMargin=17 * mm, title="꿀픽 maintest 프로젝트 정리",
                      author="소병선 (Claude Opus 5.5 작성 보조)", subject="기능·예외 처리·DB ERD")
frame = Frame(M, 17 * mm, W - 2 * M, H - 32 * mm, id="f")
doc.addPageTemplates([PageTemplate("cover", [frame]), PageTemplate("main", [frame], onPage=deco)])
FW, FH = W - 2 * M, H - 32 * mm


def img(path, max_h=None, caption=None):
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(str(path)).getSize()
    max_h = (max_h or FH - 14) - (18 if caption else 0)  # frame padding + caption line
    scale = min(FW / iw, max_h / ih)
    out = [Image(str(path), iw * scale, ih * scale)]
    if caption:
        out.append(P(caption, "note"))
    return out


st = []
# ---------------- 표지 ----------------
st += [Spacer(1, 55 * mm), P("꿀픽(KkulPick)", "sub"), Spacer(1, 4),
       P("maintest 프로젝트 정리", "title"), Spacer(1, 6),
       P("기능 목록 · API · 예외 처리 · DB ERD · 테스트 · 남은 과제", "sub"), Spacer(1, 30 * mm),
       T([["항목", "내용"],
          ["기준 브랜치 / 커밋", "maintest = part/소병선-backend-test · d0a46f8 (김호진 웹 병합 반영)"],
          ["작성일", "2026-11-25"],
          ["ERD 추출 방법", "격리 PostgreSQL(pgvector 0.8.7 / PG17)에 alembic 마이그레이션 전체 적용 후 "
                         "pg_catalog에서 직접 추출 (member 0004, catalog 0012, support 0002)"],
          ["작성", "소병선(백엔드·DB) — Claude Opus 5.5 작성 보조"]], [40, 128]),
       NextPageTemplate("main"), PageBreak()]

# ---------------- 1. 개요 ----------------
st += [H1("1. 프로젝트 개요"),
       P("꿀픽은 쇼핑몰 상품·식품 화면을 캡처해 분석하고, 가격 비교·대체 상품·알레르기 경고를 보여주는 팀 프로젝트입니다. "
         "Chrome 확장·모바일 앱이 화면을 보내면 백엔드가 분석 작업을 만들고, 분석 워커가 OCR(Vision)과 추천 서비스를 호출해 "
         "결과 카드를 돌려줍니다. 상품 데이터는 수집기가 주기적으로 백엔드 내부 API로 적재합니다."),
       H2("1.1 구성 요소"),
       T([["구성", "위치", "담당", "기술", "maintest 상태"],
          ["백엔드 API", "services/api", "소병선", "FastAPI · SQLAlchemy(async) · Alembic", "운영 수준 기능 구현, 통합 테스트 완료"],
          ["DB", "infra/db", "소병선", "PostgreSQL 17 + pgvector, DB 3개 분리", "마이그레이션 18개 적용"],
          ["분석 워커", "services/dev_runtime", "소병선", "Python 워커, 작업 lease 프로토콜", "동작 (OCR·추천 호출)"],
          ["추천·임베딩", "services/recommendation", "박정우", "pgvector 검색, 임베딩 워커, LLM 랭커(선택)", "동작, 운영 DB 연동"],
          ["수집기", "services/collector", "최준서", "도매꾹 라이브 / 11번가 오프라인, Outbox 전송", "관측 적재 연동, 확장·check-in 미연동"],
          ["이미지 분석", "services/vision", "이다온", "OCR HTTP 개발 틀", "개발 틀(진행 중)"],
          ["관리자 웹", "apps/web", "김호진", "Next.js 프록시 + 정적 콘솔(7개 화면)", "병합 완료, 서버 API 연동"],
          ["Chrome 확장", "apps/extension", "서지웅", "MV3 · React 18 · TS · Vite", "실제 API 연동"],
          ["모바일", "apps/mobile", "배정 필요", "Expo 58 · React Native 0.88", "실제 API 연동(시작 코드 이상)"],
          ["관리자(구)", "apps/admin", "배정 필요", "Next.js", "API 연결 확인용 시작 코드"]],
         [22, 31, 15, 50, 50]),
       H2("1.2 전체 흐름"),
       *B([f"수집: 수집기 → {code('POST /internal/v2/crawl-runs/{run_id}/observations')} → 정규화·검증 → offers/가격·URL 이력, "
           "변경 시 embedding_jobs 큐 적재(트리거)",
           "임베딩: embedding_worker가 큐를 32개씩 가져와 벡터 생성 → product/food_embeddings 저장 (실패 8회 시 보류)",
           f"분석: 확장/모바일 캡처 → {code('POST /analyses')}(202) → 워커가 claim·heartbeat → Vision OCR + 추천 "
           "→ complete/fail → 클라이언트 폴링",
           "추천: URL로 카탈로그 상품 매칭 → 벡터 후보 → 알레르기 규칙 제외 → 랭킹 → 카드(신선도 stale 표시 포함)",
           "관리: 관리자 웹 콘솔 → /v2/admin/* (가입 승인, 상담, 제휴, 카탈로그 삭제, 통계)"]),
       PageBreak()]

# ---------------- 2. DB / ERD ----------------
st += [H1("2. 데이터베이스 구조 (ERD)"),
       P("PostgreSQL 컨테이너 하나에 <b>독립 DB 3개</b>를 둡니다(스키마 분리가 아님). 각 DB는 owner(마이그레이션)·app(CRUD) 계정이 "
         "분리되어 있고 업무 테이블은 모두 app 스키마에 있습니다. <b>DB 사이에는 외래키가 없고</b>, 회원 ID 같은 참조는 앱 코드가 "
         "보장합니다(아래 그림의 점선)."),
       T([["DB", "테이블", "역할", "마이그레이션"],
          ["kkulpick_member", "13", "회원·세션·선호(알레르기)·구독·청구·결제(모의)·관리자 계정/세션/감사·탈퇴·요청 제한", "0001–0004"],
          ["kkulpick_catalog", "20", "상품 공통/상세·판매처 리스팅·가격/URL/변경 이력·수집 실행/관측·리스팅 확장·제휴·분석 작업·"
                                   "임베딩 계약/큐/벡터·원재료", "0001–0012"],
          ["kkulpick_support", "3", "상담 대화·메시지·운영 설정", "0001–0002"]], [30, 13, 107, 18]),
       Spacer(1, 4),
       P("범례 — <b>PK</b> 기본키, <b>FK</b> 외래키, <b>UQ</b> 유니크 제약 포함, <i>기울임</i>은 NULL 허용 컬럼. "
         "실선 화살표는 FK(1 → N), 점선은 논리 참조입니다. 원본 해상도 PNG·SVG는 PDF와 같은 폴더에 함께 제공합니다.", "note"),
       PageBreak()]
st += img(D / "erd_overview.png", caption="그림 1. 전체 구조 — DB 3개와 FK·DB 간 논리 참조") + [PageBreak()]
st += img(D / "erd_member.png", caption="그림 2. kkulpick_member (회원·구독·결제·관리자)") + [PageBreak()]
st += img(D / "erd_catalog.png", caption="그림 3. kkulpick_catalog (상품·수집·제휴·분석·임베딩) — 확대는 erd_catalog.svg 참고") + [PageBreak()]
st += img(D / "erd_support.png", max_h=95 * mm, caption="그림 4. kkulpick_support (고객센터)")
st += [H2("2.1 핵심 설계 포인트"),
       *B(["<b>상품 정체성 분리</b>: catalog_items(공통) ← products / foods(1:1 상세), offers는 (item_id, kind) 복합 FK로 "
           "상품 종류 불일치를 DB가 차단",
           "<b>리스팅 식별</b>: offers는 (source, source_listing_id, variant_key) 유니크. 삭제된 리스팅은 offer_tombstones로 "
           "오래된 관측의 부활 차단",
           "<b>이력</b>: price_history·offer_url_history·offer_changes는 관측(observation_id) 단위로 1건씩(유니크) 기록",
           "<b>임베딩 Outbox</b>: 상품 내용 변경 시 트리거가 embedding_jobs에 (item, model) 작업 적재, "
           "embedding_models.is_serving으로 서비스 중 계약 1개 유지",
           "<b>관리자 계정 분리</b>: admin_identities(가입 신청 → 승인 시 role 부여) + admin_sessions(auth_version으로 "
           "권한 변경 시 기존 세션 무효화)",
           "<b>멱등성·동시성</b>: invoices.idempotency_key, analyses.request_key, messages.client_message_id 유니크 + "
           "version 컬럼으로 낙관적 잠금"]),
       PageBreak()]

# ---------------- 3. 기능 목록 ----------------
st += [H1("3. 기능 목록")]
FEATURES = [
    ("3.1 회원·인증", [
        "회원 가입(아이디 4–16자 영숫자, 약관 동의 버전 기록), 아이디 중복 확인 — 회원·관리자 아이디 공간 통합(advisory lock)",
        "로그인/로그아웃: 무작위 토큰(32바이트) 발급, DB에는 SHA-256 해시만 저장, 7일 만료",
        "비밀번호 scrypt 해시(솔트), 비교는 상수 시간(hmac.compare_digest), 해시 계산은 스레드풀",
        "내 정보·프로필(성별·생년·중고 포함 여부·알레르기/선호) 수정 — profile_version 낙관적 잠금, 비밀번호 변경",
        "회원 탈퇴(202): 세션 삭제 후 상담·분석·이미지까지 DB 간 정리(account_deletions로 진행 상태 추적)"]),
    ("3.2 구독·결제 (개발용 모의 결제)", [
        "구독 상품 조회, 구독 신청 — Idempotency-Key 헤더 필수, 같은 키·다른 내용이면 409",
        "결제 대기 중 중복 결제 차단(PAYMENT_PENDING), 이미 구독 중이면 409",
        "내 구독 조회·해지(기간 종료 시 해지), 결제 내역, 모의 환불, 내부 모의 결제 결과 확정 API",
        "운영 환경에서 모의 결제를 막는 설정 검사(MOCK_BILLING_FORBIDDEN / INVALID_BILLING_CONFIGURATION)"]),
    ("3.3 관리자", [
        "관리자 가입 신청 → 기존 관리자가 승인(역할 부여) → 승인 전 로그인 차단(ADMIN_APPROVAL_REQUIRED)",
        "관리자 세션은 auth_version과 enabled를 매 요청 확인 → 권한 회수 즉시 반영",
        "관리자 정보(/v2/admin/me), 회원 목록, 대시보드 집계(회원·구독·당일 구독자·최근 30일/오늘 모의 결제 합계)",
        "카탈로그 상품 일괄 삭제(tombstone 기록 + 감사 로그), CLI로 관리자 권한 부여/회수(admin_cli)"]),
    ("3.4 고객센터 상담", [
        "회원: 대화 생성(진행 중 대화 1개 재사용), 목록, 메시지 조회(sequence 기반 커서), 메시지 전송",
        "client_message_id로 재전송 멱등 처리(같은 키·다른 내용이면 MESSAGE_KEY_CONFLICT)",
        "관리자: 전체 대화 목록(마지막 응답 관리자 포함), 답변, 상태 변경(version 잠금), 상담 운영 시간·부재 메시지 설정"]),
    ("3.5 상품 카탈로그·수집 적재", [
        "수집기 전용 토큰 인증 관측 적재 API — 크롤 실행 1개당 출처 1개(RUN_SOURCE_CONFLICT), 같은 관측 키 재전송 시 멱등",
        "정규화·검증 후 offers 생성/갱신, 가격·URL·내용 이력 기록, 변경 필드(changed_fields) 기록",
        "격리(quarantine) 사유: 식별자 누락, 너무 오래된 관측, 식별 충돌, 가격 급변(기본 10배), 첫 관측 정보 부족, 동시각 충돌",
        "허용 호스트·통화 목록, 상품 조회 API(/v2/offers: 종류·새상품/중고 필터, 커서 페이지)"]),
    ("3.6 리스팅 확장·신선도", [
        "리스팅 확장 API: 판매처·모델명·GTIN·옵션·식품 성분/알레르기 근거 → 상품 상세 반영(옵션 값 null은 삭제)",
        "관측보다 확장이 먼저 오면 202 pending 저장 → 첫 관측 적재 트랜잭션 안에서 자동 적용",
        "유사 상품 매칭(/v2/offers/{id}/matches): 동일 상품 → 브랜드+모델명 → 기타 순 정렬",
        "판매 확인(check-in) API: 가격·통화·재고가 같으면 last_seen_at 갱신, 카드에 seen_at·stale(기본 72시간) 표시"]),
    ("3.7 제휴·추천·링크 변환", [
        "관리자 제휴 링크 등록/수정/비활성화(version 잠금, 감사 로그), 제휴 목록",
        "공개 추천: 제휴 추천(featured), 기본 카탈로그 추천(basic, 최근 확인순)",
        "애드픽 제휴 URL 변환(/v2/links/convert): 전체 분당 60회·클라이언트별 분당 10회(DB 고정 창), "
        "미지원 URL은 400(1시간 캐시), 성공은 24시간 캐시, API 키는 서버 환경변수에만 보관"]),
    ("3.8 페이지 분석 작업", [
        "캡처 업로드(최대 2MB, PNG/JPEG/WebP 형식 검사, 요청 본문 3MB 제한) 또는 URL만으로 분석 요청(202)",
        "request_key 멱등, 사용자당 동시 진행 3개 제한(ANALYSIS_LIMIT), 마감 시간·취소·이력·데이터 삭제",
        "워커 프로토콜: claim(FOR UPDATE SKIP LOCKED) → 2분 lease·heartbeat → complete/fail, 최대 3회 시도",
        "이미지는 비공개 임시 저장소에 두고 만료 시 삭제, 결과에 알레르기 경고·추천 카드 포함"]),
    ("3.9 임베딩·추천 서비스", [
        "임베딩 계약(모델·차원·템플릿 catalog-v2: 이름|브랜드|카테고리|종류|설명) 불변 관리, 서비스 계약 교체 시 이전 계약 정리",
        "임베딩 워커: 32개 배치, 배치 실패 시 개별 재시도로 격리, 8회 실패 시 보류(exhausted) + --requeue-failed 재처리",
        "추천 HTTP 서비스: 카탈로그 URL 매칭(호스트 접미사 대응) → pgvector 후보 → 알레르기 제외 → 랭킹, 재고·신선도 필터 옵션"]),
    ("3.10 데이터 보존·운영", [
        "보존 정책 정리 작업(maintenance, 배치 500, dry-run 기본), 만료 이미지 정리",
        "/health 헬스체크, 요청마다 X-Request-ID, 개인 API 응답 Cache-Control: no-store"]),
    ("3.11 프론트엔드", [
        "관리자 웹 콘솔 7개 화면: 로그인/가입 신청, 대시보드, 상담, 제휴, 수집 상품(목록·선택 삭제·점진 로딩), 고객, 통계",
        "웹은 Next.js /backend 프록시로 API 호출, 로그인·승인·삭제 모두 서버 응답만 사용(로컬 우회 제거)",
        "Chrome 확장: 탭 URL 감지 → 캡처 → 분석 → 사이드 패널·인페이지 플로팅 카드, 로그인·알레르기 설정·구독",
        "모바일: 앱 내 브라우저 캡처 분석, 최근 기록, 로그인/가입, 마이페이지, 고객지원, 재료 필터, 프리미엄 결제"]),
]
for title, items in FEATURES:
    st += [KeepTogether([H2(title), *B(items)])]
st += [PageBreak()]

# ---------------- 4. API ----------------
st += [H1("4. API 엔드포인트 목록 (56개)"),
       P("인증 — 공개: 없음 / 회원: 회원 Bearer 토큰 / 관리자: 승인된 관리자 토큰 / 수집기·워커·결제: 서버 간 전용 토큰.", "note")]
API = [
    ("공통", [("GET", "/health", "공개", "헬스체크"), ("GET", "/v2/offers", "공개", "상품 목록(종류·상태 필터, 커서)"),
            ("GET", "/v2/offers/{offer_id}/matches", "공개", "유사 상품")]),
    ("회원·인증", [("POST", "/v2/auth/signup", "공개", "회원 가입(201)"), ("GET", "/v2/auth/login-id-availability", "공개", "아이디 확인"),
               ("POST", "/v2/auth/login", "공개", "로그인"), ("POST", "/v2/auth/logout", "회원", "로그아웃(204)"),
               ("GET", "/v2/me", "회원", "내 정보"), ("PATCH", "/v2/me/profile", "회원", "프로필 수정"),
               ("PATCH", "/v2/me/password", "회원", "비밀번호 변경"), ("POST", "/v2/me/withdrawal", "회원", "탈퇴(202)")]),
    ("구독·결제", [("GET", "/v2/subscription-plans", "공개", "구독 상품"), ("POST", "/v2/me/subscriptions", "회원", "구독 신청(Idempotency-Key)"),
               ("GET", "/v2/me/subscription", "회원", "내 구독"), ("POST", "/v2/me/subscription/cancel", "회원", "해지"),
               ("GET", "/v2/me/payments", "회원", "결제 내역"), ("POST", "/v2/me/payments/{id}/mock-refund", "회원", "모의 환불"),
               ("POST", "/internal/v2/mock-payments/{id}/resolve", "결제 테스트", "모의 결제 확정")]),
    ("관리자", [("POST", "/v2/admin/auth/signup", "공개", "관리자 가입 신청"), ("POST", "/v2/admin/auth/login", "공개", "관리자 로그인"),
             ("POST", "/v2/admin/auth/logout", "관리자", "로그아웃"), ("GET", "/v2/admin/auth/requests", "관리자", "가입 신청 목록"),
             ("POST", "/v2/admin/auth/requests/{user_id}/approve", "관리자", "가입 승인"), ("GET", "/v2/admin/me", "관리자", "관리자 정보"),
             ("GET", "/v2/admin/members", "관리자", "회원 목록"), ("GET", "/v2/admin/overview", "관리자", "대시보드 집계"),
             ("POST", "/v2/admin/catalog/offers/delete", "관리자", "상품 일괄 삭제")]),
    ("고객센터", [("POST", "/v2/support/conversations", "회원", "대화 생성"), ("GET", "/v2/support/conversations", "회원", "내 대화"),
              ("GET", "/v2/support/conversations/{id}/messages", "회원", "메시지 조회"),
              ("POST", "/v2/support/conversations/{id}/messages", "회원", "메시지 전송"),
              ("GET", "/v2/admin/support/conversations", "관리자", "전체 대화"),
              ("GET", "/v2/admin/support/conversations/{id}/messages", "관리자", "메시지 조회"),
              ("POST", "/v2/admin/support/conversations/{id}/messages", "관리자", "답변"),
              ("PATCH", "/v2/admin/support/conversations/{id}", "관리자", "상태 변경"),
              ("GET / PUT", "/v2/admin/support/settings", "관리자", "운영 설정 조회/저장")]),
    ("제휴·추천·링크", [("GET", "/v2/admin/affiliate-offers", "관리자", "제휴 목록"), ("PUT", "/v2/admin/affiliate-offers/{offer_id}", "관리자", "제휴 등록/수정"),
                  ("DELETE", "/v2/admin/affiliate-offers/{offer_id}", "관리자", "제휴 비활성화"),
                  ("GET", "/v2/recommendations/featured", "공개", "제휴 추천"), ("GET", "/v2/recommendations/basic", "공개", "기본 추천"),
                  ("POST", "/v2/links/convert", "공개(제한)", "애드픽 URL 변환 — 인증 추가 필요(#16)")]),
    ("분석", [("POST", "/analyses", "회원", "분석 요청(202)"), ("GET", "/analyses/{id}", "회원", "결과 조회(폴링)"),
            ("POST", "/analyses/{id}/cancel", "회원", "취소"), ("GET", "/v2/me/analyses", "회원", "분석 이력"),
            ("POST", "/v2/me/data-deletions", "회원", "분석 데이터 삭제"),
            ("POST", "/internal/v2/analyses/claim", "워커", "작업 가져오기"),
            ("POST", "/internal/v2/analyses/{id}/heartbeat", "워커", "lease 연장"),
            ("GET", "/internal/v2/analyses/{id}/image", "워커", "캡처 이미지"),
            ("POST", "/internal/v2/analyses/{id}/complete", "워커", "완료"), ("POST", "/internal/v2/analyses/{id}/fail", "워커", "실패/재시도")]),
    ("수집기 내부", [("POST", "/internal/v2/crawl-runs/{run_id}/observations", "수집기", "관측 적재"),
                ("POST", "/internal/v2/crawl-runs/{run_id}/extensions", "수집기", "리스팅 확장(실행 단위)"),
                ("POST", "/internal/v2/listing-extensions", "수집기", "리스팅 확장"),
                ("POST", "/internal/v2/listing-checks", "수집기", "판매 확인 check-in(최대 500건)")]),
]
rows = [["영역", "메서드", "경로", "인증", "설명"]]
for area, items in API:
    for i, (m, p, a, d) in enumerate(items):
        rows.append([area if i == 0 else "", m, code(p), a, d])
st += [T(rows, [20, 15, 70, 18, 55], zebra=False), PageBreak()]

# ---------------- 5. 예외 처리 ----------------
st += [H1("5. 예외 처리"),
       H2("5.1 공통 오류 응답 형식"),
       P("모든 오류는 같은 JSON 구조로 반환되고, 입력값·비밀번호·SQL·외부 키는 응답과 로그에 넣지 않습니다."),
       T([["필드", "의미"],
          [code("error.code"), "안정적인 오류 코드(대문자). 프론트는 이 값으로 분기"],
          [code("error.message"), "사용자에게 보여줄 한국어 메시지(코드별 고정 문구)"],
          [code("error.retryable"), "429·503일 때 true — 잠시 후 재시도 가능"],
          [code("request_id"), "요청 추적 ID(응답 헤더 X-Request-ID와 동일), 서버 로그와 대조용"],
          [code("fields"), "422 검증 오류일 때 문제 필드 위치만(값은 제외)"]], [35, 133]),
       H2("5.2 전역 예외 매핑 (services/api/kkulpick/errors.py)"),
       T([["예외", "HTTP / 코드", "처리 이유"],
          ["HTTPException(대문자 코드)", "그대로 / 해당 코드", "업무 오류를 의도대로 전달"],
          ["RequestValidationError", "422 INVALID_INPUT", "입력값을 되돌려주지 않고 필드 위치만 반환"],
          ["IntegrityError", "409 DATA_CONFLICT", "유니크·FK 위반 = 동시 요청 충돌"],
          ["ProgrammingError, DataError", "500 INTERNAL_ERROR + 스택 로그", "SQL·권한·타입 오류는 코드 결함 — 재시도 유도하지 않음"],
          ["기타 SQLAlchemyError", "503 DATABASE_UNAVAILABLE, Retry-After 3", "DB 연결 장애 등 일시적 문제"],
          ["ConnectionError, TimeoutError, gaierror", "503 DEPENDENCY_UNAVAILABLE", "내부 서비스·네트워크 일시 장애(다른 OSError는 500 유지)"],
          ["그 외 모든 Exception", "500 INTERNAL_ERROR + 스택 로그", "원인 진단 가능하게 위치 정보만 기록"],
          ["요청 본문 초과(미들웨어)", "413", "JSON 64KB, 분석 업로드 3MB — 파싱 전에 차단"]], [50, 50, 68]),
       H2("5.3 상태 코드별 업무 오류 코드"),
       T([["HTTP", "오류 코드"],
          ["400", "AFFILIATE_URL_UNSUPPORTED"],
          ["401", "AUTH_REQUIRED, INVALID_CREDENTIALS, WORKER_AUTH_REQUIRED, COLLECTOR_AUTH_REQUIRED, BILLING_TEST_AUTH_REQUIRED"],
          ["402", "PAYMENT_FAILED"],
          ["403", "ADMIN_REQUIRED, ADMIN_APPROVAL_REQUIRED, PREMIUM_REQUIRED"],
          ["404", "OFFER / ANALYSIS / CONVERSATION / PAYMENT / PLAN / SUBSCRIPTION / AFFILIATE / IMAGE / ADMIN_SIGNUP _NOT_FOUND"],
          ["409", "LOGIN_ID_TAKEN, VERSION_CONFLICT, IDEMPOTENCY_CONFLICT, REQUEST_KEY_CONFLICT, MESSAGE_KEY_CONFLICT, "
                  "PAYMENT_PENDING, PAYMENT_STATE_CONFLICT, PAYMENT_ALREADY_REFUNDED, PAYMENT_NOT_REFUNDABLE, "
                  "SUBSCRIPTION_ALREADY_ACTIVE, CONVERSATION_CLOSED, ANALYSIS_ALREADY_FINISHED, WORKER_LEASE_CONFLICT, "
                  "RESULT_CONFLICT, DOMAIN_CONFLICT, ADMIN_SIGNUP_ALREADY_PROCESSED, RUN_SOURCE_CONFLICT, "
                  "PAYLOAD_CONFLICT, EXTENSION_PAYLOAD_CONFLICT, DATA_CONFLICT"],
          ["410 / 413 / 415", "IMAGE_EXPIRED / IMAGE_TOO_LARGE / CONTENT_TYPE_UNSUPPORTED, IMAGE_FORMAT_UNSUPPORTED"],
          ["422", "INVALID_INPUT, INPUT_REQUIRED, WRONG_PASSWORD, DUPLICATE_FIELDS, DUPLICATE_OFFERS, INVALID_HOURS, INVALID_RESULT_OFFERS"],
          ["429", "AUTH_RATE_LIMITED, ANALYSIS_LIMIT, AFFILIATE_LINK_RATE_LIMITED, AFFILIATE_LINK_BUSY"],
          ["503", "DATABASE_UNAVAILABLE, DEPENDENCY_UNAVAILABLE, PAYMENT_PROVIDER_NOT_CONFIGURED, MOCK_BILLING_FORBIDDEN, "
                  "INVALID_BILLING_CONFIGURATION, AFFILIATE_LINK_UNAVAILABLE, AFFILIATE_LINK_NOT_CONFIGURED"]], [22, 146]),
       PageBreak(),
       H2("5.4 영역별 방어 로직"),
       T([["영역", "상황", "처리"],
          ["요청 제한", "무차별 로그인·가입·아이디 조회, 분석·상담 남용", "IP+작업별 분당 30회(AUTH_REQUESTS_PER_MINUTE) DB 고정 창 → 429 + Retry-After"],
          ["인증", "관리자 권한 회수·비활성", "auth_version 불일치·enabled=false 세션 즉시 거부"],
          ["인증", "회원·관리자 아이디 중복 경쟁", "advisory lock으로 두 테이블을 함께 확인 후 생성"],
          ["동시 수정", "두 관리자가 같은 데이터 저장", "version 비교 → 409 VERSION_CONFLICT(새로고침 안내)"],
          ["결제", "네트워크 재시도로 중복 결제", "Idempotency-Key + 요청 해시: 같은 요청은 같은 결과, 다른 내용은 409"],
          ["결제", "결제 결과 확인 전 재결제", "pending 결제가 있으면 409 PAYMENT_PENDING"],
          ["수집 적재", "같은 관측 재전송 / 다른 내용", "observation_key 멱등 / 409 PAYLOAD_CONFLICT"],
          ["수집 적재", "식별자 누락·오래된 관측·가격 10배 급변·동시각 충돌", "거부 대신 quarantine 상태로 보관(원인 코드 기록), 삭제된 리스팅은 tombstone으로 부활 차단"],
          ["리스팅 확장", "관측보다 먼저 도착", "202 OFFER_NOT_YET_OBSERVED로 보류 → 첫 관측 트랜잭션에서 savepoint로 적용"],
          ["분석", "워커 중단·타임아웃", "lease 만료 시 재대기(최대 3회) → WORKER_RETRIES_EXHAUSTED, 오래된 lease의 완료는 409"],
          ["분석", "과도한 요청·큰 이미지", "사용자당 진행 3개, 이미지 2MB·형식 검사, 마감 시간 경과 시 만료"],
          ["분석 워커", "백엔드·Vision·추천 일시 장애", "일시 오류는 retryable 실패로 보고, 백엔드 404/409는 lease 상실로 판단(백엔드 URL일 때만)"],
          ["임베딩", "특정 상품이 계속 실패(독성 데이터)", "배치 실패 시 개별 처리로 격리, 8회 실패 시 보류 + 운영자가 --requeue-failed"],
          ["임베딩", "DB 연결 끊김", "CONNECTION_LOST 감지 시 시도 횟수 증가 없이 재연결"],
          ["애드픽", "외부 API 400 / 장애 / 과다 요청", "400 → AFFILIATE_URL_UNSUPPORTED(1시간 부정 캐시), 연결 실패 → 503, 분당 한도 → 429"],
          ["프론트(웹)", "API 404·실패", "로컬 승인·숨김 같은 우회 없이 오류 메시지 표시, 15초 요청 시간 제한, 예전 localStorage 토큰 자동 삭제"]],
         [22, 52, 94]),
       H2("5.5 보안 요약"),
       *B(["비밀번호 scrypt, 세션 토큰은 해시만 저장, 상수 시간 비교",
           "DB 계정 분리(owner/app) — 앱 계정은 DDL·다른 DB 접근 불가, DB 간 FK 없음",
           "서버 간 API는 별도 토큰(수집기·워커·결제 테스트), 외부 키(애드픽)는 서버 .env에만",
           "오류 응답·로그에 입력값·비밀번호·SQL·토큰 미포함, 개인 응답 no-store",
           "관리자 토큰을 다른 사용자에게 넘기던 웹 우회 코드 제거(#20)"]),
       PageBreak()]

# ---------------- 6. 테스트·CI ----------------
st += [H1("6. 테스트와 CI"),
       T([["묶음", "테스트 함수 수(코드)", "최근 실행 결과 (격리 DB, 2026-11-25)"],
          ["API (services/api/tests)", "66 (파라미터 포함 89 실행)", "통합 89 통과, DB 없는 단위 35 통과"],
          ["추천·임베딩 (services/recommendation/tests)", "48", "추천+분석 워커 합계 79 통과"],
          ["분석 워커 (services/dev_runtime)", "15", "위 79에 포함"],
          ["샘플 변조 검사", "—", "32 통과, 실행 순서 반대로도 통과"],
          ["tools", "17", "—"],
          ["UI Playwright (tests/ui)", "5개 spec", "CI(PR #15)에서 실행 — 결과 확인 필요"]], [62, 44, 62]),
       H2("6.1 GitHub Actions 워크플로 (8개)"),
       T([["워크플로", "내용"],
          ["Team build", "팀 프로젝트 빌드·타입 검사"], ["Catalog API integration", "API 통합 테스트(실제 PostgreSQL)"],
          ["Database environment", "DB 초기화·권한·pgvector 검증"], ["Persistent embedding pipeline", "임베딩 큐·워커 통합"],
          ["Team development access", "팀 접근 설정 검사"], ["Team connected runtime", "서비스 연결 실행 검사"],
          ["Frontend backend integration", "웹·확장 UI ↔ 백엔드 Playwright"], ["Full development workspace", "전체 개발 환경 기동"]],
         [55, 113]),
       H1("7. 남은 과제 (devlog OPEN_ISSUES 기준)"),
       T([["#", "문제", "심각도", "다음 행동"],
          ["29", "전송 실패·격리된 상품을 수집기가 영구히 갱신 중단", "중요", "수집기·백엔드 정책 합의"],
          ["30", "백엔드 409 하나로 출처 전체 전송 중단", "중요", "409 항목 단위 처리"],
          ["31", "판매 확인 신호 — 백엔드 완료, 수집기 미호출", "중요", "수집기에서 listing-checks 호출"],
          ["32", "수집기가 확장 API(판매처·GTIN·성분) 미사용", "중요", "두 파트 계약 연결"],
          ["24", "임베딩 v2 전환 직후 추천 0건", "중요", "블루/그린 전환"],
          ["33", "새 사이트 추가 시 허용 목록 동시 변경 필요", "운영", "등록 절차·사전 확인"],
          ["25", "분석 재시도 대기(backoff) 없음", "중요", "지수 대기"],
          ["18", "워커 동시 4 vs OCR 1, 90초 타임아웃", "중요", "동시성·대기 조정"],
          ["16", "애드픽 변환 API 무인증", "중요", "offer_id 기반으로 변경"],
          ["17", "프록시 뒤 IP 제한이 전체 제한이 됨", "중요", "nginx·uvicorn 설정"],
          ["27", "알레르기 사용자 식품 추천 0건(성분 미수집)", "데이터", "#32 해결 시 해소"],
          ["04 / 19", "식품 오판 시 알레르기 검사 누락(부분 해결)", "중요", "오판 사례 수집"],
          ["26", "이미지 없는 미매칭이 OCR_FAILED·retryable", "경미", "오류 코드 분리"],
          ["21 / 22", "Vision 캐시 키, 추천 서비스 DB 연결 풀", "경미", "sha256 전체 해시 / psycopg_pool"],
          ["23", "실제 수집 원본 300건 저장소 커밋", "확인 필요", "저장소에서 제거 여부 결정"]], [14, 84, 18, 52]),
       Spacer(1, 6),
       P("웹 담당 참고: origin/part/김호진-web 브랜치 자체에는 #55(404 주소)·#20(토큰 위임) 코드가 남아 있으므로 "
         "maintest를 먼저 받아서 작업해야 합니다.", "note")]

doc.build(st)
print("ok")
