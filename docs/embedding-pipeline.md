# maintest: 상품 저장부터 DB 벡터 검색까지

이 문서의 **worker는 사람이 아니라 백엔드에서 자동 실행되는 프로그램**입니다.
백엔드 담당자가 운영하는 `embedding-worker`가 상품 벡터를 만들며, 크롤러는 기존 Observation v2로 상품 원문만 보냅니다.

## 변경된 흐름

1. 수집 API가 상품명·설명을 저장합니다.
2. 같은 DB 트랜잭션의 트리거가 공개 상품 스냅샷과 content_version을 `app.embedding_jobs`에 넣습니다.
3. embedding-worker가 작업을 임대하고 트랜잭션 밖에서 임베딩을 계산합니다.
4. 저장 직전에 상품 버전과 임대 토큰을 다시 확인하고, 벡터 저장과 작업 삭제를 한 트랜잭션으로 처리합니다.
5. 분석 worker는 OCR 상품명/검색어, 선택 영역, 사용자 조건과 경고용 성분만 추천 HTTP 서비스에 보냅니다.
6. 추천 HTTP 서비스는 검색어만 임베딩하고 `PgVectorIndex` → pgvector → 후보 상품 → 기존 안전 필터·랭커 순서로 처리합니다.

요청마다 상품 1,000개를 다운로드하거나 `reindex()`하지 않습니다. 상품 URL 조회도 DB에서 정확한 URL로 한 건 조회하므로 기존 페이지 상한의 영향을 받지 않습니다. 쿼리 문자열이 다른 URL을 합치지 않으며 외부 페이지를 직접 가져오지 않습니다.

## 모델 계약

기본값은 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384차원, CPU, 정규화 사용입니다.
가중치 revision은 `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`로 고정했습니다.
확인 출처: https://huggingface.co/api/models/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

모델명·revision·차원·입력 템플릿·정규화·prefix·대상 영역으로 계약 ID를 계산합니다.
입력 템플릿은 `catalog-v2: name | brand | category | kind | description`(빈 필드 생략)입니다. v1(name·kind·description)에서 브랜드·카테고리를 추가했으며(마이그레이션 0011), 템플릿이 바뀌면 계약 ID가 새로 생겨 전체 상품을 다시 임베딩합니다.
상품과 식품은 서로 다른 계약/테이블을 사용하며 HTTP 검색 전 계약 일치를 검사합니다.
계약 미등록·비활성화·DB 장애는 503으로 표시하고 메모리/해시 방식으로 자동 대체하지 않습니다.

`RECO_EMBEDDER=hash`는 모델 다운로드 없는 연결·동시성 테스트 전용입니다. 해당 health 응답의 `business_ready`는 false입니다.
의미 검색 품질을 평가하는 설정이 아닙니다. 기본 실제 모델과 테스트용 해시는 서로 다른 계약 ID를 사용합니다.
실제 모델 파일은 이미지 빌드 때 다운로드하고 실행 때는 오프라인으로 로드합니다. 최초 빌드에는 네트워크·디스크·메모리가 필요합니다. 유료 LLM 호출은 기본 설정(rule 랭커)에 없습니다.

## 실행

기존 환경 설정 파일과 DB 볼륨을 유지한 상태에서 maintest를 체크아웃합니다.

```sh
git switch maintest
python tools/workspace.py init
python tools/workspace.py up --scope integrated
```

전체 개발 환경은 `--scope full`도 지원합니다. NAS에서 `NAS_VISION=1`을 사용한다면 기존 명령이 새 임베딩 구성도 포함합니다.

```sh
sudo sh infra/nas/nas.sh up
sudo sh infra/nas/nas.sh logs embedding-init embedding-worker recommendation
```

구동 순서는 마이그레이션(0008) → embedding-init(owner 권한으로 계약·HNSW 인덱스 등록 및 기존 상품 작업 생성) → embedding-worker/recommendation입니다.
기존 실상품과 가상 상품 모두 자동으로 작업 대상이 됩니다. 최초 처리 중에는 아직 벡터가 없는 상품이 검색 결과에 나오지 않을 수 있습니다.
크롤러와 추천 컨테이너에는 owner 자격증명을 주지 않으며, owner는 일회성 embedding-init에서만 사용합니다.

일반 PC에서 초기 재계산을 끝까지 기다리며 확인하려면:

```sh
docker compose --env-file infra/db/.env --env-file services/api/.env --env-file infra/workspace/.env -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f infra/integration/embeddings.compose.yaml stop embedding-worker
docker compose --env-file infra/db/.env --env-file services/api/.env --env-file infra/workspace/.env -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f infra/integration/embeddings.compose.yaml run --rm embedding-worker python -m services.recommendation.embedding_worker --drain
docker compose --env-file infra/db/.env --env-file services/api/.env --env-file infra/workspace/.env -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f infra/integration/embeddings.compose.yaml start embedding-worker
```

`--drain`은 지연 재시도·임대 중인 작업이나 보류(parked)된 작업이 남으면 성공으로 보고하지 않습니다. 종료된 worker의 임대는 최대 5분 뒤 회수합니다.
`--requeue-failed`는 보류된 작업의 재시도 횟수를 초기화해 다시 처리하게 합니다(원인을 고친 뒤 실행).
모델을 바꾸면 RECO_MODEL_NAME / RECO_MODEL_REVISION / RECO_MODEL_DIMENSIONS를 함께 설정하고 이미지를 다시 빌드해야 합니다. 기존 계약 내용은 수정하지 않습니다.
`--bootstrap`은 같은 영역의 이전 serving 계약을 `is_serving=false`로 내리고 그 대기 작업을 지웁니다. **새 계약의 벡터가 다 만들어질 때까지 추천 후보가 비어 보입니다**(OPEN_ISSUES #24). 운영 중 계약을 바꿀 때는 재임베딩이 끝난 뒤 트래픽을 여는 절차가 필요합니다.

## 실패·동시성 처리

- 상품 원문이 바뀌면 버전을 올리고 최신 스냅샷으로 작업을 교체합니다. 가격만 바뀌면 다시 임베딩하지 않습니다.
- 변경 트랜잭션이 롤백되면 작업도 남지 않습니다.
- 여러 worker가 `FOR UPDATE SKIP LOCKED`로 서로 다른 작업을 가져갑니다.
- 계산 중 상품이 변경되거나 임대가 만료되면 오래된 결과를 저장하거나 새 작업을 삭제하지 않습니다.
- 실패는 원문 없이 오류 클래스만 기록하고 최대 300초 간격으로 재시도합니다. `EMBEDDING_MAX_ATTEMPTS`(기본 8)회 실패하면 `available_at=infinity`, `last_error='exhausted:<오류>'`로 보류하고 다시 가져가지 않습니다.
- worker는 `EMBEDDING_BATCH_SIZE`(기본 32)개씩 임대해 한 번에 추론합니다. 묶음 추론이 실패하면 건별로 다시 시도해 문제 있는 상품만 실패 처리합니다.
- 추론이 끝난 묶음은 **한 트랜잭션으로 저장**합니다(상품마다 커밋하지 않음). 상품별 저장은 savepoint라 한 건이 실패해도 그 건만 되돌리고 재시도합니다. 측정: 상품당 5.3ms → 2.8ms.
- PyTorch CPU 스레드는 `RECO_TORCH_THREADS`(기본 `min(4, 코어 절반)`)입니다. 코어를 전부 쓰면 스레드끼리 경쟁해 오히려 느립니다(14코어 측정: 14스레드 초당 34건, 4스레드 초당 268건). Vision OCR과 CPU를 나눠 쓰는 NAS에서는 2~4를 권장합니다.
- 판매 종료/품절/의심 상품은 후보 검색과 최종 offer 매핑에서 제외합니다.
- 공개 상품 텍스트만 벡터로 저장합니다. 개인 OCR·검색어·프로필은 임베딩 작업 테이블에 저장하지 않습니다.
- 식품의 원재료 데이터가 DB에 없으면 기존의 보수적 알레르기/회피 필터를 유지합니다. OCR로 본 한 상품의 성분을 다른 추천 상품의 성분으로 간주하지 않습니다.

## 검증

`Persistent embedding pipeline` GitHub Actions는 maintest push에도 실행됩니다.
실제 PostgreSQL/pgvector에서 등록·재실행, 1,001개 기존 상품 처리, 변경 무효화, 롤백, 임대 회수, 동시 요청, 실패 재시도, 상품/식품 분리, 판매 상태 및 HTTP 경로를 확인합니다.
별도 CPU 모델 검사에서는 고정된 실제 모델을 내려받아 네트워크 없는 컨테이너에서 쿼리/문서 호환성과 간단한 한국어 관련성 사례를 확인합니다.
이 검사는 서비스 연결과 회귀 검증이며 실제 쇼핑 데이터 전체에 대한 추천 품질·운영 성능 보장은 아닙니다.

운영 서버에 접속하거나 운영 DB를 변경하는 작업은 이 브랜치 수정에 포함하지 않습니다. 배포 후에는 실제 데이터의 임베딩 작업 잔량과 대표 검색어 결과를 확인해야 합니다.
