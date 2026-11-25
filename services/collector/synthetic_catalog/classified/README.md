# 기존 백만 건 보존 + 계층 분류 보완본

기존 v1 생성기/원본 데이터/테스트 적재기는 변경하지 않는다. 이 모듈은 기존 샘플을 읽어
별도 classified-v2 뷰를 만들고 부족한 카테고리만 추가한다. 원본과 보완본을 합쳐 중복 집계하지 않는다.

## 분류 근거

현재 작업 트리와 로컬 2개/원격 추적 19개(HEAD 별칭 포함), 총 21개 저장된 Git ref를
checkout/fetch 없이 조사했다. 캐시된 ref 기준이며 원격의 최신 브랜치를 조회했다고 주장하지 않는다.
contracts/collected-product.v1.md와 추천 모델에는 category/brand 자유 문자열이 있고,
현재 DB 스키마에는 catalog_items.kind=product/food만 있다. 공식 3단계 상품 분류 코드표는 발견되지 않았다.
웹의 상담 category(결제/계정 등)와 공급자의 원시 category ID를 상품 분류표로 오인하지 않았다.
팀 스키마/계약은 읽기만 하고 수정하지 않았다. 운영 DB를 조회하지 않았다.

taxonomy.provisional.json은 임시 대분류 11개/중분류 22개/소분류 44개와 상품 프로필을 정의한다.
디지털·가전, 패션, 식품, 생활·주방, 가구, 뷰티, 스포츠, 자동차, 도서, 반려동물,
기존 완구 데이터를 보존하기 위한 완구·취미를 포함한다.
모든 임시 ID는 SYN-CAT-*이며 team_category_id는 null, 상태는 pending_team_approval이다.
현재 팀 kind 구분은 유지하되 펫 먹거리 등을 인간 식품/알레르기 데이터로 임의 승격하지 않는다.

## 실제 기존 데이터의 부족 사항

v1은 laptop/phone/food/book/clothing/furniture/cosmetics/toys 각 125000개, 총 1000000개였다.
대분류로 합치면 디지털 250000개, 다른 기존 6개 대분류는 각 125000개이며
생활·주방/스포츠/자동차/반려동물은 없었다. 상품명은 일반형이고 brand/specifications/3단계 경로가 없다.
새 뷰는 원래 category 의미를 유지하며 구체적인 소분류에 배분하고 가상 브랜드·모델·규격·가격을 보완한다.
노트북은 사무용/게이밍, 휴대폰은 일반/폴더블 등 호환되는 프로필로만 배분한다.
각 프로필의 native KRW/USD 가격 범위와 중고 허용 여부를 명시한다.
가격은 테스트용 개연성 범위이며 실제 시장 시세/환율/실판매가라고 주장하지 않는다.
브랜드/모델도 모두 SYNTHETIC 표시가 있는 가상 명칭이다.
식품/뷰티·세제/먹거리 같은 지정 소모품은 신품만 만들며 원재료/알레르기/안전/확정 재고는 null이다.

## 균형 배분과 총건수

기존 대분류 최대 건수(디지털 250000)를 줄이지 않고 각 대분류를 같은 수로 맞춘다.
따라서 기존 1000000 + 부족분 1750000 = 보완본 전체 2750000개이다.
카테고리마다 100만 개가 아니다. 대분류 각 250000 / 중분류 각 125000 / 소분류 각 62500개다.
원본 100만 파일은 따로 보존되며, 보완본의 처음 100만 행은 같은 record_id/source_listing_id/variant_key를 유지한다.
보완본에서 달라진 이름·가격은 origin의 원래 값과 원래 observation_key로 추적한다.
추가 175만 건은 SYNTHETIC-ADD-* 별도 ID 공간이다. 새 observation_key는 보완된 body 기준으로 계산한다.
전체의 고유 상품 수는 2750000이며 원본 복사본까지 더해 3750000으로 보고하지 않는다.

## 실행

```powershell
# 저장소 루트. 출력은 코드/Git 및 원본 데이터 폴더와 분리한다.
$python = '.\.venv\Scripts\python.exe'
$source = 'C:\Users\junse\Documents\Codex\2026-11-21\swproject-services-collector-domeggook-live-api\work\synthetic-scale-validation\1000000'
$output = 'C:\Users\junse\Documents\Codex\2026-11-21\swproject-services-collector-domeggook-live-api\work\synthetic-classified-balanced'
& $python -m services.collector.synthetic_catalog.classified --source $source --plan
& $python -m services.collector.synthetic_catalog.classified --source $source --output $output
& $python -m services.collector.synthetic_catalog.classified --source $source --output $output --verify --report C:\검증보고서\classified.json --sample C:\검증보고서\classified-samples.jsonl
```

minimum-total 기본값은 전체 100만이다. 계획은 기존 분포를 보존하면서 균등화하므로 실제 총건수는 더 클 수 있다.
명시적 minimum-total 상향도 가능하지만 로컬 생성 상한 1000만을 넘기면 거부한다.
10k 이하 part별 스트리밍/해시/atomic manifest와 lock을 사용하며 메모리에 전체 ID set을 올리지 않는다.
중단 시 같은 source/output/taxonomy/설정으로 재개한다. 설정 변경/손상/알 수 없는 파일은 초기화하지 않는다.
완성됐지만 manifest 기록 직전에 중단된 part는 결정적 재생성 해시와 같을 때만 채택한다.
보고서·샘플 경로를 원본이나 뷰 내부로 지정하면 원본/manifest 덮어쓰기를 막기 위해 거부한다.

## 검증과 향후 팀 매핑

검증기는 전 행의 필수값·고유 ID 순서·소분류 부모 경로·상품명/브랜드/모델/규격·가격 범위·통화·상태·
synthetic 마커·원문 출처·관측키·part 해시를 검사한다. 원본 100만 행과 보완본의 ID/원래 값/URL/지역/상태도 대조한다.
원본 모든 파일의 해시를 생성 전후와 최종 검증에서 비교한다.
각 레코드는 검증된 임시 소분류 중 하나에만 속한다. 낯선 원본 category는 무작위 매핑하지 않고 거부한다.

mapping.pending.json은 공식 분류표가 정해질 때 채울 링크 테이블의 빈 초안이다.
mapping.py는 source_reference/revision이 있는 공식 3단계 JSON과 임시 소분류→공식 소분류 매핑을 검증한다.
link_record는 기존 레코드를 수정하지 않고 별도 매핑 행만 만든다. 누락 매핑은 null/unmapped로 남긴다.
팀의 수용 승인이 없는데 매핑 결과를 운영 DB에 전송하지 않는다.

이 모듈에는 HTTP/SQL/운영 적재 기능이 없다. 새 스키마는 v1 test_api도 거절하며
현재 Observation v2/팀 API가 3단계 카테고리를 영속화한다고 주장하지 않는다.
기존 NAS runtime Docker COPY는 v1 상위 *.py만 포함하므로 이 로컬 보완 도구를 이미지에서 쓰려면
후속 배포 검토에서 classified 하위 패키지를 명시적으로 포함해야 한다. 기존 배포 파일은 이번에 바꾸지 않는다.
