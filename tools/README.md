# 검증 스크립트

[METHODS.md](../METHODS.md) 4장에서 쓰는 도구. 비밀값은 들어 있지 않다(env는 `gen_env.py`가 매번 무작위로 만든다).

| 파일 | 용도 | 사용 |
| --- | --- | --- |
| `gen_env.py` | 격리 검증용 `verify.env`(DB_PORT 55433) / `verify-in.env`(5432) 생성 | `python gen_env.py <저장소 밖 임시폴더>` |
| `run-all.sh` | 통합 테스트: 추천+워커 → API, 반대 순서, 샘플 변조 | 테스트 컨테이너 안에서 `bash /s/run-all.sh` (`/src`=저장소, 읽기 전용) |
| `ui.compose.yaml` | 관리자 웹(53000)+API(58000) 화면 검증용 덮어쓰기 | `docker compose -p kkulpick-ui ... -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f <devlog>/tools/ui.compose.yaml up -d` (경로는 `infra/db` 기준 상대 경로) |
| `sim-worker.compose.yaml` | 분석 워커를 Vision 끊긴 상태로 띄우는 시뮬레이션 덮어쓰기 | `../sim/README.md` 참고 |
| `extract_schema.sh` | 마이그레이션 적용된 DB에서 app 스키마 TSV 추출 | `bash extract_schema.sh <postgres 컨테이너> <출력폴더>` |
| `erd/Dockerfile` | docgen 이미지(graphviz, 나눔 글꼴, poppler, reportlab) | `docker build -t kkulpick-docgen tools/erd` |
| `erd/make_erd.py` | TSV → ERD 4장(전체+DB별) png/svg/pdf | `docker run --rm -v <폴더>:/d kkulpick-docgen python /d/make_erd.py /d` |
| `erd/make_pdf.py` | 프로젝트 정리 PDF (본문은 d0a46f8 시점 스냅샷 — 갱신 후 사용) | `... python /d/make_pdf.py /d /o` |
