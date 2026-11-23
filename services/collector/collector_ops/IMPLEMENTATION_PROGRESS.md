# 통합 수집 최종 체크포인트 — 2026-11-23

## 원본과 보호
- 실제반영: C:/Users/junse/Python/swproject, branch part/최준서-collector, HEAD a8be688.
- 작업시작374개파일해시/Git index/.env baseline과수정전백업은Codex work/master-20261123에있다.
- 이번변경은unified_live와이체크포인트뿐. 기존API/DB/추천/비전/도매꾹등팀파일은변경하지않았다.
- Git stage/commit/push0, NAS배포0/기존8개서비스변경0, 운영DB/API전송0. 합성275만건미사용/미변경.

## 구현 완료
- discovery: 공개directory19후보, 중복제거/범위제한/metadata·상품품질·독립grant 분리, 자동비활성등록.
- analysis/parser: graph참조/Schema/OG/microdata/native선택자/검색form/OpenSearch, 가격·이미지·카테고리·GTIN.
- fleet: 허가generic만사이트별child격리/재시작/취소/잠금/8개상한. 공식API는기존profile.
- feeds/public_sources: 공식피드/MCP read-only소량검증, 운영feed는권한/판매처증거/예산/변경큐/7200주기.
- food: 기존evidence재사용, 원재료표·비율·함유/혼입/unknown분리, exactGTIN OFF3.6 policy-gated어댑터.
- uncertainty/outbox유실hold/내용중복억제/metadata변경집계, token FILE검증, 기존가격/권한검사유지.
- Compose독립8서비스profile, secrets/state/health/restart/logging, NAS별도release검사/승인배포스크립트.
- Linux기본/브라우저Docker이미지빌드및실행확인. cleanCOPY context exporter로기존cache권한변경안함.

## 실제 검증 결과
- 전체482테스트+하위145모두통과, 실패/오류/skip0(offline socket차단), 이전436+135포함.
- eBayUsed: Production OAuth1+검색1+상세1 HTTP200, 정상1/보류0, 정확재고모름/조작안함.
- Smartify피드3개v2통과, HTML308hold. Yappy피드3개v2/팀모델통과, MCP3개/HTML은판매처·상태보류.
- 실제feed3개→loopback HTTP→임시SQLite: ACK3, replay3, listing/event3유지/중복0, 원문영구파일0.
- WindowsEdge와LinuxDockerChromium에서합성JS/XHR정규화통과. 실제쇼핑몰JS는미검증.
- Compose2.20.1전profile config통과, 기본Linux컨테이너5개+실제Chromium컨테이너실행통과.
- NASSSH 비대화형정식인증실패(publickey,password), 서버명령/서비스조작안함.

## 실패와 해결
- SQLite context manager가연결을닫지않아Windows임시폴더정리잠금: closing+commit수정/회귀통과/자체temp정리.
- DockerBuildKit PROTOCOL_ERROR와원본protectedcache: legacybuilder+외부cleanCOPY context로빌드성공.
- 브라우저이미지node/libatomic없음: libatomic1선설치, /ms-playwright경로선설정/읽기권한으로빌드·비root실행성공.
- native seller/condition없는결과와308은데이터를만들거나우회하지않고보류/hold유지.

## 남은 일/재개
1. MASTER_GUIDE.md / MASTER_API_STATUS.md / MASTER_CONTRACT.md와Codex outputs/master-*최종증거를읽는다.
2. NAS인증/별도release/volumeUID10001/HTTPS API도달성을관리자와확인한다. 기존worktree는pull/reset금지.
3. 소스별저장·재사용·가격·host/currency·60초policy·예산을확정. YES24/파트너소스는권한전DB금지.
4. 팀전용격리endpoint에서실제PG ACK/멱등성/판매처·리퍼·개봉·식품확장계약검증. 현재localSQLite는대체증명아님.
5. 승인된소스만COLLECTOR_RUN_APPROVED와별도COLLECTOR_DELIVERY_APPROVED를설정해개별profile실행.
6. 실제쇼핑몰JS/장기24h스케줄/NAS재시작복구는미검증. 코드·Mock·Docker·live·NAS/PG상태를구분한다.

외부요청없이재개: python -m services.collector.unified_live.discovery --state-dir <새localstate> --plan
상태: python -m services.collector.unified_live.discovery --state-dir <기존localstate> --status
최종전체회귀: pytest services/collector -o cache_dir=<repo외절대cache> --junitxml=<외부report>
단,전체회귀명령의정확한대상/오프라인환경변수는최종보고서참조(운영/integration수동스크립트제외).
소스는원본에이미반영되어있고Codex폴더→원본복사작업은추가로필요없다.
