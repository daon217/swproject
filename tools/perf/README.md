# 성능·메모리 측정 스크립트 (2026-11-25, #66·#67)

| 파일 | 용도 |
| --- | --- |
| `make_images.py` | 합성 한글 상품 페이지 8장 생성 (docgen 이미지 안에서 `python make_images.py`, 출력 `/o`) |
| `compose.yaml` + `drive.py` | Vision 격리 스택(redis·api·worker)과 분석 부하 발생기. `docker stats`로 워커 메모리 관찰 |
| `ocr_mem6.py <bucket> <batch>` | 폭이 다른 120줄 인식 시 메모리. bucket=40이면 입력 폭 고정 |
| `ocr_mem7.py same\|three` | 같은 모양 반복 시 메모리(누수 vs 모양별 증가 구분) |
| `bench_embed.py` + `run.sh` | 임베딩 DB 쓰기 처리량(hash), `BATCH_TX=1`이면 배치 커밋 |
| `st_bench2.py` | MiniLM CPU 스레드 수별 처리량 |
Vision 실험은 `docker run --rm --memory 7g -v <models 볼륨>:/home/app/.paddleocr ... kkulpick-vision-check:local python /d/ocr_mem6.py 40 6` 형태로 실행.
