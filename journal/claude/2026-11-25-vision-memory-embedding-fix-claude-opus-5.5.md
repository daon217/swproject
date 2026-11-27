# [Claude Opus 5.5] 개발일지 · 2026-11-25 #66 Vision 메모리 · #67 임베딩 속도 수정

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` `9247330`(#66), `426a5da`(#67) → **maintest 반영**(fast-forward, #59 b51ffdc 포함)
- 상태: **#66 해결, #67 해결.** 원인 분석은 [측정 일지](2026-11-25-vision-memory-embedding-speed-claude-opus-5.5.md)

## #66 Vision 워커 메모리

### 해결
- `ocr_engine.py`
  - 검출 입력을 항상 `OCR_CANVAS_WIDTH×HEIGHT`(1920×1600) 캔버스로: 크면 비율 유지 축소, 남는 오른쪽·아래는 흰색. 반환 좌표는 `scale`로 나눠 원래 이미지 기준.
  - `OCR_DET_LIMIT_SIDE` 1280(설정화, 기존 736 하드코딩).
  - 인식기 `resize_norm_img`를 감싸 입력 폭을 `REC_WIDTH_RATIOS`(8,20 → 384/960px) 중 하나로만, `REC_BATCH_NUM`=1.
- `celery_app.py`: `worker_max_memory_per_child`(1,500,000KiB), `task_reject_on_worker_lost=False`(죽은 작업 재투입 금지 — 같은 이미지가 새 자식도 죽이는 연쇄 종료 방지).
- compose(nas, integration): Vision 워커 `mem_limit` `${VISION_WORKER_MEM_LIMIT:-3g}`.
- `kkulpick_vision/README.md` 4장에 설정 표.

### 선택 과정 (전부 측정)
| 시도 | 결과 | 판단 |
| --- | --- | --- |
| 인식 폭 1920 하나 | 메모리 고정, 그러나 페이지 3~4배 느려짐(22→99초) — 워커 90초 대기 초과 | 버림 |
| 폭 40/25/16 비교(89줄) | 39.4 / 22.6 / 14.8초, 결과 일치 94/96/97% | 짧은 폭이 빠르고 정확 |
| 폭 2가지(8,20) vs 3가지(6,12,20) | 13.2초·0.70GiB vs 13.1초·1.85GiB | **2가지 채택** |
| 검출 캔버스 1920 + det 736 | 성분 재현율 42% → **20%로 하락**(글자가 너무 작아짐) | 버림 — 회귀를 측정으로 잡음 |
| 캔버스 1920 + **det 1280** | 재현율 **48%**(원래 42%), 0.83GiB | **채택** |

### 검증
- 8장(높이 2600~4200 포함)을 한 프로세스에서 연속 처리: **최대 852MiB, 증가 없음**(원래는 5번째 장에서 6.7GiB → 강제 종료).
- 격리 Vision 스택(redis·api·worker) 분석 11건: 워커 메모리 498~561MiB 유지, 강제 종료 0회, 페이지 처리 시간 원래와 같거나 빠름(예: 11.6→4.6초, 21.7→20.6초).
- 재현율은 합성 이미지 기준이고 절대값이 낮은 건 #62(정제 규칙) 영향. 미확인: 실제 쇼핑몰 캡처에서의 재현율, NAS에서의 절대 시간.

## #67 임베딩 속도

### 해결
- `embedders.py`: `torch_threads()` — `RECO_TORCH_THREADS`, 기본 `min(4, 코어 절반)`. `SentenceTransformerEmbedder`가 생성 시 `torch.set_num_threads`. 추천 HTTP 서비스의 쿼리 임베딩도 같은 클래스라 함께 적용.
- `embedding_worker.once()`: 추론은 트랜잭션 밖, 저장은 **배치 전체를 한 트랜잭션**으로. `finish()`의 중첩 트랜잭션이 savepoint가 되어 한 건 실패는 그 건만 되돌리고 `retry()`.
- `embeddings.compose.yaml`에 `RECO_TORCH_THREADS` 전달, `docs/embedding-pipeline.md` 설명.

### 검증
- DB 쓰기(모델 제외, 3000건, 실제 `once()` 루프): **4.08 → 2.61 ms/건**(수정 전 커밋을 worktree로 띄워 같은 조건 비교).
- 모델: 14스레드 34/s → 4스레드 268/s(측정 일지).
- 새 테스트: `test_batch_commit_isolates_a_failing_write`(배치 안 한 건이 실제 SQL 오류 → 그 건만 재시도, 나머지 저장, 트랜잭션 종료 확인), `test_torch_threads_default_avoids_oversubscription`.
- 격리 DB 전체: 추천+워커 **83**, API 90, 샘플 변조 32 — 두 실행 순서 모두 통과. 추천 묶음 실행 시간 11.7s → 6.4s.

## 남은 과제
- NAS에서 `docker stats`로 Vision 워커 메모리 재확인, 임베딩 처리량 확인(필요하면 `RECO_TORCH_THREADS` 2로).
- #62(정제 규칙), #63(1장 캡처), #64(작업 예외) — Vision 남은 문제.
