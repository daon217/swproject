"""한국어 ERD: extract_schema.sh 결과(TSV)를 받아 한글 테이블명·컬럼명이 들어간 ERD를 만든다.
docgen 이미지 안에서: python make_erd_ko.py <tsv 폴더> <출력 폴더>
"""
import csv
import html
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
FONT = "NanumGothic"
DBS = OrderedDict([
    ("member", ("회원 DB (kkulpick_member) · 회원·구독·결제·관리자", "#2563eb", "#dbeafe")),
    ("catalog", ("상품 DB (kkulpick_catalog) · 상품·수집·식품·제휴·분석·임베딩", "#059669", "#d1fae5")),
    ("support", ("상담 DB (kkulpick_support) · 고객센터", "#d97706", "#fef3c7")),
])
TABLE_KO = {
    "members": "회원", "member_preferences": "회원 알레르기·선호", "sessions": "회원 로그인 세션",
    "subscription_plans": "구독 상품", "subscriptions": "구독", "invoices": "청구서", "payments": "결제",
    "admin_accounts": "관리자 권한(구 방식)", "admin_identities": "관리자 계정", "admin_sessions": "관리자 세션",
    "admin_audit": "관리자 감사 기록", "account_deletions": "회원 탈퇴 요청", "auth_attempts": "요청 횟수 제한",
    "catalog_items": "상품 공통", "products": "일반 상품 상세", "foods": "식품 상세(원재료·알레르기)",
    "offers": "판매처 상품(리스팅)", "offer_url_history": "판매 주소 이력", "price_history": "가격 이력",
    "offer_changes": "상품 변경 이력", "offer_tombstones": "삭제된 리스팅 표시", "crawl_runs": "수집 실행",
    "crawl_observations": "수집 관측 원본", "listing_extensions": "리스팅 확장(판매처·식품 근거)",
    "affiliate_offers": "제휴 링크", "analyses": "페이지 분석 작업", "catalog_admin_audit": "상품 관리 감사 기록",
    "embedding_models": "임베딩 모델 계약", "embedding_jobs": "임베딩 작업 대기열", "product_embeddings": "상품 벡터",
    "food_embeddings": "식품 벡터", "ingredients": "원재료 사전(미사용)", "ingredient_embeddings": "원재료 벡터(미사용)",
    "conversations": "상담 대화", "messages": "상담 메시지", "support_settings": "상담 운영 설정",
}
COL_KO = {
    "action": "작업", "actor_id": "수행자 ID", "affiliate_url": "제휴 링크 주소", "after_data": "변경 후 값",
    "allergen_notice_raw": "알레르기 표시 원문", "allergens_declared": "신고 알레르기 코드", "amount": "금액",
    "analysis_id": "분석 ID", "attempt": "시도 횟수", "attempts": "시도 횟수", "audit_id": "감사 ID",
    "auth_version": "권한 버전", "availability": "판매 상태", "available_at": "처리 가능 시각", "away_message": "부재 안내",
    "before_data": "변경 전 값", "benefits": "혜택", "billing_mode": "결제 방식(모의/실제)", "birth_date": "생년월일",
    "body": "내용", "brand": "브랜드", "bucket": "제한 키", "cancel_at_period_end": "기간 끝 해지 예약",
    "canonical_name": "표준 이름", "category": "카테고리", "change_id": "변경 ID", "change_kind": "변경 종류",
    "changed_fields": "바뀐 필드", "client_message_id": "클라이언트 메시지 ID", "code": "코드", "color": "색상",
    "completed_at": "완료 시각", "condition": "상품 상태(새/중고/미확인)", "condition_observed_at": "상태 확인 시각",
    "consent_at": "동의 시각", "consent_version": "동의 문서 버전", "content_observed_at": "내용 확인 시각",
    "content_version": "내용 버전", "conversation_id": "대화 ID", "created_at": "생성 시각",
    "cross_contact_raw": "혼입 표시 원문", "currency": "통화", "current_url": "현재 판매 주소", "days": "운영 요일",
    "deadline": "마감 시각", "deleted_at": "탈퇴 시각", "description": "설명",
    "description_observed_at": "설명 확인 시각", "detail_observed_at": "상세 확인 시각", "dimensions": "벡터 차원",
    "document_prefix": "문서 접두어", "embedding": "벡터 값", "embedding_id": "벡터 ID", "enabled": "사용 여부",
    "encoder_name": "모델 이름", "end_time": "종료 시간", "ends_at": "종료 시각", "entitlement_end": "이용 만료 시각",
    "error_code": "오류 코드", "evidence_status": "근거 상태", "expires_at": "만료 시각", "extension_id": "확장 ID",
    "food_id": "식품 ID", "food_observed_at": "식품 정보 확인 시각", "gender": "성별", "gtin": "바코드(GTIN)",
    "idempotency_key": "중복 방지 키", "identifiers": "상품 식별자 목록", "image_hash": "이미지 해시",
    "image_id": "이미지 ID", "image_url": "대표 이미지", "image_urls": "이미지 목록", "include_used": "중고 포함",
    "ingredient_id": "원재료 ID", "ingredients": "원재료 목록", "ingredients_raw": "원재료 원문",
    "input_template": "입력 문장 형식", "interval": "결제 주기", "invoice_id": "청구서 ID", "is_serving": "서비스 중",
    "item_id": "상품 ID", "kind": "종류(상품/식품)", "last_changed_at": "마지막 변경 시각",
    "last_checked_at": "마지막 확인 시각", "last_error": "마지막 오류", "last_seen_at": "마지막 판매 확인 시각",
    "lease_token": "작업 점유 토큰", "lease_until": "점유 만료 시각", "login_id": "로그인 아이디",
    "manufacturer": "제조사", "message_id": "메시지 ID", "method": "결제 수단", "model_id": "모델 계약 ID",
    "model_name": "모델명", "model_number": "모델 번호", "mpn": "제조사 부품번호", "name": "이름",
    "next_sequence": "다음 메시지 순번", "normalize": "정규화 여부", "normalized_payload": "정리된 원본 데이터",
    "observation_id": "관측 ID", "observation_key": "관측 키", "observed_at": "관측 시각", "offer_id": "판매 상품 ID",
    "offer_ids": "추천 상품 ID 목록", "options": "옵션", "owner_id": "회원 ID", "page_revision": "페이지 버전",
    "page_session_id": "페이지 세션 ID", "page_url": "페이지 주소", "paid_at": "결제 시각", "partner_name": "제휴사",
    "password_hash": "비밀번호 해시", "payload_hash": "데이터 해시", "payment_id": "결제 ID", "period_end": "기간 끝",
    "period_start": "기간 시작", "plan_id": "구독 상품 ID", "price": "가격", "price_history_id": "가격 이력 ID",
    "price_observed_at": "가격 확인 시각", "product_id": "상품 ID", "profile_version": "프로필 버전",
    "provider": "결제사", "query_prefix": "검색 접두어", "received_at": "수신 시각", "refunded_at": "환불 시각",
    "request_hash": "요청 해시", "request_id": "요청 ID", "request_key": "요청 키", "result_metadata": "분석 결과 정보",
    "revision": "모델 리비전", "role": "역할", "run_id": "수집 실행 ID", "schema_version": "형식 버전",
    "selected_domain": "분석 종류", "seller_id": "판매자 ID", "seller_name": "판매자 이름", "sender": "보낸 쪽",
    "sender_id": "보낸 사람 ID", "sequence_no": "순번", "shipping_fee": "배송비", "shipping_observed_at": "배송비 확인 시각",
    "singleton": "단일 행 키", "size": "크기", "snapshot": "임베딩 입력 사본", "source": "수집처",
    "source_listing_id": "수집처 상품 ID", "start_time": "시작 시간", "started_at": "시작 시각", "starts_at": "시작 시각",
    "state": "처리 상태", "status": "상태", "status_observed_at": "판매 상태 확인 시각", "subscription_id": "구독 ID",
    "target": "대상(상품/식품)", "target_id": "대상 ID", "token_hash": "토큰 해시", "updated_at": "수정 시각",
    "updated_by": "수정한 관리자", "url": "주소", "url_history_id": "주소 이력 ID", "url_observed_at": "주소 확인 시각",
    "user_id": "회원 ID", "valid_from": "사용 시작", "valid_to": "사용 끝", "value": "값", "variant_key": "옵션 키",
    "variant_signature": "옵션 서명", "version": "버전", "window_start": "제한 시작 시각", "worker_id": "작업자 ID",
}
COL_KO_BY_TABLE = {  # 같은 컬럼 이름이 테이블마다 뜻이 다른 경우
    ("member_preferences", "kind"): "종류(알레르기/기피/선호)", ("member_preferences", "value"): "항목 값",
    ("crawl_observations", "state"): "적재 결과", ("listing_extensions", "state"): "적용 결과",
    ("admin_audit", "target_id"): "대상 회원 ID", ("auth_attempts", "attempts"): "요청 횟수",
    ("offer_tombstones", "deleted_at"): "삭제 시각",
}
TYPE_KO = {"uuid": "UUID", "text": "문자", "boolean": "참/거짓", "jsonb": "JSON", "date": "날짜", "vector": "벡터",
           "integer": "정수", "int": "정수", "bigint": "큰 정수", "smallint": "작은 정수", "timestamptz": "시각",
           "numeric": "숫자", "uuid[]": "UUID 목록"}
LOGICAL = [  # DB를 넘는 참조(외래키 없음, 앱 코드가 보장)
    ("support", "conversations", "member", "members", "회원"),
    ("support", "messages", "member", "members", "보낸 사람"),
    ("catalog", "analyses", "member", "members", "요청 회원"),
    ("catalog", "affiliate_offers", "member", "admin_identities", "수정 관리자"),
    ("catalog", "catalog_admin_audit", "member", "admin_identities", "수행 관리자"),
]


def load(db):
    tables, fks = OrderedDict(), []
    for r in csv.reader(open(SRC / f"{db}.tsv", encoding="utf-8"), delimiter="\t"):
        _, t, _, col, typ, nn, pk, fk, uq = r
        if t == "alembic_version":
            continue
        typ = (typ.replace("timestamp with time zone", "timestamptz").replace("character varying", "varchar")
               .replace("numeric(20,4)", "numeric"))
        typ = TYPE_KO.get(typ, typ)
        tables.setdefault(t, []).append((col.strip('"'), typ, nn == "t", pk == "PK", bool(fk), uq == "U"))
        for ref in filter(None, fk.split(",")):
            rt, rc = ref.split(".")
            fks.append((t, col.strip('"'), rt, rc))
    return tables, fks


def node(db, t, cols, full=True):
    color, light = DBS[db][1], DBS[db][2]
    rows = [f'<TR><TD COLSPAN="4" BGCOLOR="{color}"><FONT COLOR="white" POINT-SIZE="13"><B>{html.escape(TABLE_KO.get(t, t))}</B></FONT>'
            f'<BR/><FONT COLOR="white" POINT-SIZE="8">{t}</FONT></TD></TR>']
    if full:
        for col, typ, nn, pk, fk, uq in cols:
            key = "기본키" if pk else ("외래키" if fk else ("고유" if uq else ""))
            kc = {"기본키": "#b45309", "외래키": "#2563eb", "고유": "#7c3aed"}.get(key, "#000000")
            bg = light if pk else "white"
            keycell = f'<FONT COLOR="{kc}" POINT-SIZE="7"><B>{key}</B></FONT>' if key else " "
            ko = html.escape(COL_KO_BY_TABLE.get((t, col)) or COL_KO.get(col, col))
            ko = f"<B>{ko}</B>" if pk else (ko if nn else f"<I>{ko}</I>")
            rows.append(f'<TR><TD ALIGN="LEFT" BGCOLOR="{bg}" PORT="{col}_w">{keycell}</TD>'
                        f'<TD ALIGN="LEFT" BGCOLOR="{bg}">{ko}</TD>'
                        f'<TD ALIGN="LEFT" BGCOLOR="{bg}"><FONT COLOR="#94a3b8" POINT-SIZE="8">{col}</FONT></TD>'
                        f'<TD ALIGN="LEFT" BGCOLOR="{bg}" PORT="{col}_e"><FONT COLOR="#64748b" POINT-SIZE="8">{html.escape(typ)}</FONT></TD></TR>')
    return (f'"{db}.{t}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="{color}">'
            + "".join(rows) + "</TABLE>>];")


HEAD = f'''digraph G {{
  graph [rankdir=LR, fontname="{FONT}", nodesep=0.35, ranksep=0.9, pad=0.3, bgcolor="white"];
  node [shape=plaintext, fontname="{FONT}", fontsize=10];
  edge [fontname="{FONT}", fontsize=8, color="#475569", arrowhead=crow, arrowtail=tee, dir=both];
'''
LEGEND = ('기본키 · 외래키 · 고유 = 제약 조건, <I>기울임</I> = 비어 있을 수 있음, '
          '선 끝 까마귀발 = 여러 행(1:N)')


def render(name, dot):
    (OUT / f"{name}.dot").write_text(dot, encoding="utf-8")
    for fmt in ("png", "svg", "pdf"):
        args = ["dot", f"-T{fmt}", str(OUT / f"{name}.dot"), "-o", str(OUT / f"{name}.{fmt}")]
        if fmt == "png":
            args.insert(1, "-Gdpi=150")
        subprocess.run(args, check=True)
    (OUT / f"{name}.dot").unlink()


data = {db: load(db) for db in DBS}
for db, (title, color, _) in DBS.items():
    tables, fks = data[db]
    out = [HEAD, f'  label=<<B>{html.escape(title)}</B><BR/><FONT POINT-SIZE="10">테이블 {len(tables)}개 · {LEGEND}</FONT>>; labelloc=t; fontsize=18;']
    out += ["  " + node(db, t, c) for t, c in tables.items()]
    for t, col, rt, rc in fks:
        out.append(f'  "{db}.{rt}":"{rc}_e":e -> "{db}.{t}":"{col}_w":w;')
    out.append("}")
    render(f"ERD_{ {'member': '회원', 'catalog': '상품', 'support': '상담'}[db] }DB".replace(" ", ""), "\n".join(out))

out = [HEAD, '  label=<<B>꿀픽 DB 전체 구조</B><BR/><FONT POINT-SIZE="10">실선 = 외래키(1:N) · 점선 = DB 사이 논리 참조(외래키 없음, 앱 코드가 보장)</FONT>>; labelloc=t; fontsize=18;']
for db, (title, color, light) in DBS.items():
    tables, fks = data[db]
    out.append(f'  subgraph cluster_{db} {{ label=<<B>{html.escape(title)}</B>>; style="rounded,filled"; fillcolor="{light}"; color="{color}"; fontsize=14;')
    out += ["    " + node(db, t, c, full=False) for t, c in tables.items()]
    out.append("  }")
    seen = set()
    for t, col, rt, rc in fks:
        if (rt, t) not in seen:
            seen.add((rt, t))
            out.append(f'  "{db}.{rt}" -> "{db}.{t}";')
for sdb, st, tdb, tt, label in LOGICAL:
    out.append(f'  "{tdb}.{tt}" -> "{sdb}.{st}" [style=dashed, color="#94a3b8", label="{label}"];')
out.append("}")
render("ERD_전체구조", "\n".join(out))
missing = sorted({c for db in DBS for cols in data[db][0].values() for c, *_ in cols if c not in COL_KO})
print("ok; 번역 없는 컬럼:", missing)
