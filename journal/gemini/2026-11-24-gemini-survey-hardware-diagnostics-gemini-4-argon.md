# [Gemini 4 Argon] 개발일지 · 2026-11-24 전체 구조·CI 실패 규명·헤놀로지(i5-6600) 하드웨어 분석 및 16개 문제점 진단 (#48)

- 날짜: 2026-11-24 (기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-19 (초기 구조 파악), 2026-11-23 10:06~11:25 및 13:14~13:17 (전수 조사·하드웨어/성능/도메인 분석)
- 상태: 해결 (읽기 전용 진단 및 설계·운영 분석 완료; 발견된 코드 문제들의 실제 수정 여부는 개별 이슈 번호로 구분)
- 브랜치 / 커밋: 문서는 `devlog`; 점검 대상 [`origin/main` `32f08ba`](https://github.com/daon217/swproject/commit/32f08ba), [`origin/maintest` `2d444b0`](https://github.com/daon217/swproject/commit/2d444b0ee4e1c181701c8491c77800b9c30f2e88), [`origin/part/최준서-collector` `b1f45f9`](https://github.com/daon217/swproject/commit/b1f45f9), [`origin/codex/separate-admin-signup` `52c486e`](https://github.com/daon217/swproject/commit/52c486e)
- 관련 파일: `tests/ui/console.spec.js:23`, `tests/ui/guest-floating.spec.js:28`, `apps/web/pages/counseling/index.js:355`, `apps/web/pages/affiliate/index.js:919`, `apps/mobile/src/ui/BasicRecommendations.tsx:1`, `infra/nas/README.md:1`, `infra/nas/vision.compose.yaml:1`, `services/api/migrations/versions/catalog.sql:1`
- 작성 AI: Gemini 4 Argon

## 문제점
1. 병렬 AI 개발로 전환하기 위해 저장소 전체 아키텍처(3개 독립 PostgreSQL DB, FastAPI 백엔드, Vision 8100, pgvector 추천, 수집기, 확장/모바일/관리자 웹)와 원격 브랜치 20개·PR 14개·GitHub Actions 9종의 진행 상태를 코드 변경 없이 정확히 파악해야 했다.
2. 당시 `origin/main`에서 `Team connected runtime`(Run `45035799528`)과 `Frontend backend integration`(Run `44495089917`) 두 CI 워크플로가 반복 실패하고 있었으나 백엔드/OCR 장애인지 프런트엔드 테스트 불일치인지 구분되어 있지 않았다.
3. 기존 NAS 문서(`infra/nas/README.md`)는 Synology DS918+(Celeron J3455, AVX 미지원) 기준으로 작성되어 있어, 실제 운영 예정 하드웨어인 **헤놀로지(Xpenology, Intel Core i5-6600, 16GB RAM, 5.4TB HDD/RAID)** 에서 PaddleOCR과 Sentence-Transformers(`paraphrase-multilingual-MiniLM-L12-v2`) 컨테이너가 정상 구동되는지 및 리소스 병목이 어디인지 확인이 필요했다.
4. `maintest`(`2d444b0`)까지 반영된 시점에서 남아 있는 저장소 전체의 구조적 문제점을 전수 출력해야 했다.

## 원인
- **CI 실패 2건의 코드 원인(확인한 사실)**:
  1. `Team connected runtime`(`tests/ui/console.spec.js`): `tools/integration_smoke.py --image /tmp/ingredients.png --collector`는 100% 통과했으나, 커밋 `c7d8cdf`(`origin/part/김호진-web` 병합) 및 `d126928`에서 실제 서버 연동 모드(`!demo`)일 때의 문구 3곳이 변경된 반면 테스트 셀렉터는 옛 문구를 찾고 있었다.
     - `tests/ui/console.spec.js:23`: `'답변 추가'` 대기 → 실제 화면(`apps/web/pages/counseling/index.js:355`)은 `'답변 보내기'` 렌더링
     - `tests/ui/console.spec.js:29`: `'상담 설정을 DB에 저장했습니다.'` 대기 → 실제 화면(`apps/web/pages/counseling/index.js:554`)은 `'상담 설정을 팀 서버 DB에 저장했습니다.'` 렌더링
     - `tests/ui/console.spec.js:38`: `'제휴상품을 저장했습니다.'` 대기 → 실제 화면(`apps/web/pages/affiliate/index.js:919`)은 `'새 제휴 상품을 서버에 등록했습니다.'` 렌더링
  2. `Frontend backend integration`(`tests/ui/guest-floating.spec.js:28`): 커밋 `e7f7007`에서 모바일 비회원 화면(`apps/mobile/src/ui/BasicRecommendations.tsx`)의 `'상품'`/`'식품'` 전환 버튼을 삭제하고 `GUEST_DOMAIN = 'product'`로 고정했으나, 테스트는 `for (const platform of ['extension', 'mobile'])` 루프에서 모바일에도 `'식품'` 버튼 클릭을 시도해 60초 타임아웃이 발생했다.
- **하드웨어 문서와 실제 서버 사양 차이(확인한 사실)**:
  - Celeron J3455(Apollo Lake)는 AVX 명령어가 없어 x86_64 PyTorch/PaddlePaddle 바이너리 실행 시 `SIGILL`이 발생하지만, 사용자의 실제 서버 CPU인 **Intel Core i5-6600(6세대 Skylake, 4코어 4스레드, 3.3~3.9GHz)** 은 `AVX`, `AVX2`, `FMA3`, `SSE4.1/4.2`를 네이티브 지원한다.
- **파이프라인 및 브랜치 간 단절(확인한 사실)**:
  - 수집기(`origin/part/최준서-collector` `b1f45f9`)가 추출한 식품 원재료(`food_evidence`)와 상품 매칭 메타데이터(`matching_profile`)를 받아 저장할 백엔드 DB 컬럼과 API 계약이 없었고, `PgCatalog`는 빈 성분 배열을 반환하고 있었다. 또한 `analysis_worker.py`가 단일 스레드 순차 폴링 구조였다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. 원격 브랜치·Actions 로그·커밋 diff만 읽기 전용으로 대조하고 로컬 미커밋 파일은 보존 | 사용자의 로컬 작업물(`apps/mobile`) 훼손 없이 정확한 행 단위 원인 규명 가능 | 코드 수정은 별도 지시 후 진행해야 함 | ✅ |
| B. 조사 단계에서 임의로 로컬 브랜치를 전환하거나 테스트 파일을 바로 수정 | 즉시 패치 가능 | 사용자가 요청한 "파일 수정 없이 파악만 해둘 것" 제약 위반 | |

## 해결 (적용 내용)
1. **초기 아키텍처 및 원격 브랜치·CI 전수 조사 보고**:
   - 3개 독립 DB(`kkulpick_catalog`, `kkulpick_member`, `kkulpick_support`)의 `owner`/`app` 권한 분리, 마이그레이션 계보, 20개 브랜치 및 9개 GitHub Actions 워크플로 상태를 정리했다.
2. **CI 실패 2건의 팀 공유용 Discord 마크다운 및 diff 패치 작성**:
   - Discord에서 표 문법이 깨지지 않도록 리스트·인용구·`diff` 블록으로 `tests/ui/console.spec.js`(23, 29, 38행)와 `tests/ui/guest-floating.spec.js`(28~31행 `if (platform === 'extension')` 분기) 수정안을 작성해 제공했다. (실제 코드 반영은 이후 Claude 세션 #01 `2e2a806`에서도 동일 원인으로 확인·적용됨.)
3. **헤놀로지(`i5-6600`, `16GB RAM`, `5.4TB`) 구동성·메모리·처리 속도 분석**:
   - **명령어 호환성**: i5-6600의 AVX/AVX2 지원으로 Docker 컨테이너(`postgres`, `api`, `vision-api`, `vision-worker`, `recommendation`, `embedding-worker`, `analysis-worker`) 전부를 NAS 한 대에서 구동 가능함을 확인했다.
   - **메모리 예산**: 전체 스택 상주 메모리 합계를 약 **4.5 ~ 5.8GB**(PostgreSQL ~0.35GB, API/정리 ~0.25GB, Vision+Redis ~1.5~2.2GB, Recommendation ~0.7~0.9GB, Embedding Worker ~0.7~0.9GB, Analysis Worker ~0.1GB)로 산출하여 16GB RAM에서 10GB 이상 여유가 있음을 확인했다.
   - **CPU/디스크 튜닝 포인트**: 4코어 4스레드 환경에서 `embedding-worker` 대량 backfill 시 CPU 경합을 막기 위한 `OMP_NUM_THREADS`/`MKL_NUM_THREADS` 제한 필요성과, 5.4TB HDD RAID에서 반복 크롤링 시 불필요한 Random Write 및 재임베딩을 막기 위한 `payload_hash` 단락 평가(Short-circuit) 설계를 도출했다.
4. **저장소 전체 5개 영역 16개 문제점 도출**:
   - ① CI UI 테스트 불일치 2건, ② 관리자 가입 백엔드(`codex/separate-admin-signup`) 미병합 및 웹 로컬 데모 우회 위험, ③ 수집기(`part/최준서-collector`) 미병합, ④ 카탈로그 DB 식품 원재료 부재·상품 매칭 메타데이터 부재·11번가 수집기 백엔드 어댑터 미연결·분석 워커 단일 스레드 블로킹(4대 파이프라인 한계), ⑤ NAS 스레드 제한·고객센터 운영시간 안내 미연결·모의 결제/비밀번호 재설정 미구현을 체계화했다.
5. **상품(`product`) vs 식품(`food`) 구별 구조 검증**:
   - DB 스키마(`app.catalog_items.kind`, `app.products`, `app.foods`, 지연 제약 트리거 `app.check_item_subtype()`, `app.offers` 복합 FK), 수집기(`infer_entity_kind`), 백엔드 확장 적재(`DOMAIN_CONFLICT` 격리), 추천 엔진(`PgCatalog`의 `kind` 필터) 전 구간에서 상품과 식품이 분리되어 동작함을 검증해 설명했다.

## 왜 그렇게 해결했는지
코드를 수정하기 전에 전체 브랜치의 분기 상태와 하드웨어 제약, 실패 중인 CI의 정확한 원인을 먼저 분리해야 이미 해결된 문제를 중복 작업하거나 다른 팀원 파트와 충돌하는 일을 막을 수 있기 때문이다.

## 검증
- `git fetch --all --prune`, `gh run list`, `gh run view` 및 커밋 diff(`c7d8cdf`, `e7f7007`, `2d444b0`, `b1f45f9`, `11e006d`)를 통해 모든 파일 경로와 줄 번호를 실제 코드와 대조했다.
- 이 단계는 읽기 전용 조사·진단 작업이므로 저장소 파일을 수정하지 않았고, 사용자의 로컬 워킹트리(`C:\Users\user\swproject`)의 미커밋 변경 사항이 그대로 보존됨을 확인했다.

## 남은 과제 / 주의
- 이 진단에서 도출한 16개 문제점 중 **「4. 수집기 ↔ 백엔드 데이터 계약 및 분석/추천 파이프라인 한계」 4개 항목**은 사용자의 후속 지시에 따라 Gemini가 `maintest`에서 직접 해결했다([#49·#50](2026-11-24-gemini-catalog-extensions-food-evidence-gemini-4-argon.md), [#51·#52](2026-11-24-gemini-elevenst-adapter-concurrent-worker-ci-gemini-4-argon.md)).
- 나머지 항목 중 UI 테스트(#01), 관리자 백엔드 병합(#08) 등은 이후 `part/소병선-backend-test`에서 처리되었고, 아직 남아 있는 운영·연동 과제는 [OPEN_ISSUES.md](../../OPEN_ISSUES.md)에서 관리한다.
