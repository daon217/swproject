"""Build Graphviz ERDs from the TSV schema dumps (run inside a container with graphviz + fonts-nanum)."""
import csv, html, subprocess, sys
from collections import OrderedDict, defaultdict
from pathlib import Path

D = Path(sys.argv[1])
FONT = "NanumGothic"
DBS = OrderedDict([
    ("member", ("kkulpick_member · 회원·구독·결제·관리자", "#2563eb", "#dbeafe")),
    ("catalog", ("kkulpick_catalog · 상품·수집·제휴·분석·임베딩", "#059669", "#d1fae5")),
    ("support", ("kkulpick_support · 고객센터 상담", "#d97706", "#fef3c7")),
])
DESC = {
    "members": "회원", "member_preferences": "알레르기·선호", "sessions": "회원 세션", "subscription_plans": "구독 상품",
    "subscriptions": "구독", "invoices": "청구서", "payments": "결제(모의)", "admin_accounts": "회원 기반 관리자 권한",
    "admin_identities": "관리자 계정(가입 승인)", "admin_sessions": "관리자 세션", "admin_audit": "관리자 감사 로그",
    "account_deletions": "회원 탈퇴 요청", "auth_attempts": "인증/요청 횟수 제한",
    "catalog_items": "상품 공통(정체성)", "products": "일반 상품 상세", "foods": "식품 상세(원재료·알레르기)",
    "offers": "판매처 리스팅", "offer_url_history": "URL 이력", "price_history": "가격 이력", "offer_changes": "변경 이력",
    "offer_tombstones": "삭제된 리스팅 표식", "crawl_runs": "수집 실행", "crawl_observations": "수집 관측(원본)",
    "listing_extensions": "리스팅 확장(매칭·식품 근거)", "affiliate_offers": "제휴 링크", "analyses": "페이지 분석 작업",
    "catalog_admin_audit": "카탈로그 감사 로그", "embedding_models": "임베딩 계약(모델)", "embedding_jobs": "임베딩 작업 큐",
    "product_embeddings": "상품 벡터", "food_embeddings": "식품 벡터", "ingredients": "원재료 사전",
    "ingredient_embeddings": "원재료 벡터", "conversations": "상담 대화", "messages": "상담 메시지",
    "support_settings": "상담 운영 설정",
}
# Logical references that cannot be FKs (different DB, or by design)
LOGICAL = [
    ("support", "conversations", "owner_id", "member", "members", "user_id"),
    ("support", "messages", "sender_id", "member", "members", "user_id"),
    ("catalog", "analyses", "owner_id", "member", "members", "user_id"),
    ("catalog", "affiliate_offers", "updated_by", "member", "admin_identities", "user_id"),
    ("catalog", "catalog_admin_audit", "actor_id", "member", "admin_identities", "user_id"),
    ("catalog", "catalog_admin_audit", "offer_id", "catalog", "offers", "offer_id"),
    ("member", "admin_audit", "actor_id", "member", "admin_identities", "user_id"),
]

def load(db):
    tables = OrderedDict()
    fks = []
    with open(D / f"{db}.tsv", encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            _, t, _, col, typ, nn, pk, fk, uq = r
            if t == "alembic_version":
                continue
            typ = (typ.replace("timestamp with time zone", "timestamptz").replace("character varying", "varchar")
                      .replace("numeric(20,4)", "numeric").replace("integer", "int"))
            tables.setdefault(t, []).append((col, typ, nn == "t", pk == "PK", bool(fk), uq == "U"))
            for ref in filter(None, fk.split(",")):
                rt, rc = ref.split(".")
                fks.append((t, col, rt, rc))
    return tables, fks

def node(db, t, cols, full=True):
    color, light = DBS[db][1], DBS[db][2]
    rows = [f'<TR><TD COLSPAN="3" BGCOLOR="{color}" PORT="__t"><FONT COLOR="white" POINT-SIZE="13"><B>{t}</B></FONT>'
            f'<BR/><FONT COLOR="white" POINT-SIZE="9">{html.escape(DESC.get(t, ""))}</FONT></TD></TR>']
    if full:
        for col, typ, nn, pk, fk, uq in cols:
            key = "PK" if pk else ("FK" if fk else ("UQ" if uq else ""))
            kc = {"PK": "#b45309", "FK": "#2563eb", "UQ": "#7c3aed"}.get(key, "#000000")
            name = f"<B>{col}</B>" if pk else (col if nn else f"<I>{col}</I>")
            bg = light if pk else "white"
            keycell = f'<FONT COLOR="{kc}" POINT-SIZE="8"><B>{key}</B></FONT>' if key else " "
            rows.append(f'<TR><TD ALIGN="LEFT" BGCOLOR="{bg}" PORT="{col}_w">{keycell}</TD>'
                        f'<TD ALIGN="LEFT" BGCOLOR="{bg}">{name}</TD>'
                        f'<TD ALIGN="LEFT" BGCOLOR="{bg}" PORT="{col}_e"><FONT COLOR="#64748b" POINT-SIZE="9">{html.escape(typ)}</FONT></TD></TR>')
    return (f'"{db}.{t}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="{color}">'
            + "".join(rows) + "</TABLE>>];")

HEAD = f'''digraph G {{
  graph [rankdir=LR, fontname="{FONT}", nodesep=0.35, ranksep=0.9, pad=0.3, splines=true, bgcolor="white"];
  node [shape=plaintext, fontname="{FONT}", fontsize=10];
  edge [fontname="{FONT}", fontsize=8, color="#475569", arrowhead=crow, arrowtail=tee, dir=both];
'''

def render(name, dot):
    (D / f"{name}.dot").write_text(dot, encoding="utf-8")
    for fmt in ("png", "svg", "pdf"):
        args = ["dot", f"-T{fmt}", str(D / f"{name}.dot"), "-o", str(D / f"{name}.{fmt}")]
        if fmt == "png":
            args.insert(1, "-Gdpi=150")
        subprocess.run(args, check=True)

data = {db: load(db) for db in DBS}

for db, (title, color, _) in DBS.items():
    tables, fks = data[db]
    out = [HEAD, f'  label=<<B>{html.escape(title)}</B>  (app schema, 테이블 {len(tables)}개)>; labelloc=t; fontsize=18;']
    out += ["  " + node(db, t, c) for t, c in tables.items()]
    for t, col, rt, rc in fks:
        out.append(f'  "{db}.{rt}":"{rc}_e":e -> "{db}.{t}":"{col}_w":w [dir=both, arrowhead=crow, arrowtail=tee];')
    for sdb, st, sc, tdb, tt, tc in LOGICAL:
        if sdb == db and tdb == db:
            out.append(f'  "{db}.{tt}":"{tc}_e":e -> "{db}.{st}":"{sc}_w":w [style=dashed, color="#94a3b8", label="논리 참조"];')
    out.append("}")
    render(f"erd_{db}", "\n".join(out))

# Overview: tables only, three clusters, cross-DB logical edges
out = [HEAD.replace("rankdir=LR", "rankdir=LR, compound=true"),
       '  label=<<B>꿀픽 maintest DB 전체 구조</B> — 실선: 외래키(FK) · 점선: DB 간 논리 참조(FK 없음, 앱 코드에서 보장)>; labelloc=t; fontsize=18;']
for db, (title, color, light) in DBS.items():
    tables, fks = data[db]
    out.append(f'  subgraph cluster_{db} {{ label=<<B>{html.escape(title)}</B>>; style="rounded,filled"; '
               f'fillcolor="{light}"; color="{color}"; fontsize=14;')
    out += ["    " + node(db, t, c, full=False) for t, c in tables.items()]
    out.append("  }")
    for t, col, rt, rc in fks:
        out.append(f'  "{db}.{rt}" -> "{db}.{t}";')
for sdb, st, sc, tdb, tt, tc in LOGICAL:
    out.append(f'  "{tdb}.{tt}" -> "{sdb}.{st}" [style=dashed, color="#94a3b8", label="{sc}"];')
out.append("}")
render("erd_overview", "\n".join(out))
print("ok")
