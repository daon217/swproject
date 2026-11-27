-- Supabase SQL editor에서 한 번 실행
create table if not exists crawl_products (
  id bigserial primary key,
  site text not null,            -- 플랫폼 이름 (platform-urls.md)
  url text not null,
  name text,
  price numeric,                 -- 단일 가격일 때만. AggregateOffer면 null
  price_low numeric,
  price_high numeric,
  currency text,                 -- 항상 KRW (원화 고정)
  orig_currency text,            -- 사이트에서 가져온 원래 통화
  fx_rate numeric,               -- 변환에 쓴 환율 (KRW면 1)
  brand text,
  image text,
  availability text,
  source text,                   -- jsonld | og
  kind text,                     -- 상품 | 식품 | 미분류
  channel text,                  -- 일반 | 중고 | 직구
  review text,                   -- 보류 사유 (null이면 정상)
  ingredient_text text,          -- 원재료 글자 (이미지 참조뿐이면 null)
  allergen_text text,            -- 페이지의 알레르기 표시 원문
  allergens_contains text[],     -- 직접 함유 (정규화된 이름)
  allergens_trace text[],        -- 같은 제조시설 등 교차오염 가능
  ingredient_images text[],      -- OCR 후보 이미지 URL
  allergen_status text,          -- read | read_empty | image_only | unreadable (image_only/unreadable은 '안전'이 아니라 '확인 필요')
  fetched_at timestamptz not null default now(),
  unique (site, url)
);

-- 사이트별 시도 결과 (막힌 이유 = 발표용 시행착오 자료)
create table if not exists crawl_site_log (
  id bigserial primary key,
  site text not null,
  status text not null,          -- ok | no_products | blocked_403 | blocked_429 | captcha | robots_disallowed | error
  detail text,
  pages_visited int default 0,
  products_found int default 0,
  run_at timestamptz not null default now()
);
