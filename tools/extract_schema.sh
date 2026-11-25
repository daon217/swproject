#!/usr/bin/env bash
# 마이그레이션이 적용된 DB 컨테이너에서 app 스키마의 테이블·컬럼·PK·FK·UQ를 TSV로 뽑는다 (ERD 입력).
# 사용: bash extract_schema.sh <postgres 컨테이너 이름> <출력폴더>
set -euo pipefail
CT=$1; OUT=$2; mkdir -p "$OUT"
for db in member catalog support; do
docker exec "$CT" psql -U postgres -d "kkulpick_$db" -At -F $'\t' -c "
SELECT 'T', c.relname, a.attnum, a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull,
 coalesce((SELECT 'PK' FROM pg_constraint k WHERE k.conrelid=c.oid AND k.contype='p' AND a.attnum=ANY(k.conkey)),''),
 coalesce((SELECT string_agg(f.relname||'.'||fa.attname, ',') FROM pg_constraint k JOIN pg_class f ON f.oid=k.confrelid
   JOIN LATERAL unnest(k.conkey,k.confkey) u(l,r) ON true JOIN pg_attribute fa ON fa.attrelid=f.oid AND fa.attnum=u.r
   WHERE k.conrelid=c.oid AND k.contype='f' AND u.l=a.attnum),''),
 coalesce((SELECT 'U' FROM pg_constraint k WHERE k.conrelid=c.oid AND k.contype='u' AND a.attnum=ANY(k.conkey) LIMIT 1),'')
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
WHERE n.nspname='app' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum" > "$OUT/$db.tsv"
echo "$db: $(cut -f2 "$OUT/$db.tsv" | sort -u | wc -l) tables"
done
