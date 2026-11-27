# [GPT-6 (Codex)] 개발일지 · 2026-11-24 API 의존성·본문 제한·실행환경 감사 보완 (#44)

- 날짜: 2026-11-24 (누락 보완 기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-06
- 상태: 부분 해결 — 당시 작업 범위 기준, 최신 운영 완료 판정 아님
- 브랜치 / 커밋: 문서는 `devlog`; 코드 근거 [`74d0e3c`](https://github.com/daon217/swproject/commit/74d0e3c4a50879b7029a7e4f88a3a30a5d4ef480), [`0c2bff5`](https://github.com/daon217/swproject/commit/0c2bff56d04a085e8e92e1889afcfd4f5fc63105)
- 관련 파일: [services/api/kkulpick/limits.py:5](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/services/api/kkulpick/limits.py#L5); [services/api/kkulpick/api.py:35](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/services/api/kkulpick/api.py#L35); [services/api/tests/test_contract.py:25](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/services/api/tests/test_contract.py#L25); [services/api/Dockerfile:1](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/services/api/Dockerfile#L1); [infra/workspace/compose.yaml:1](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/infra/workspace/compose.yaml#L1)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 당시 상세 모델 버전은 미확인.

> 사용자 정정에 따라 실제 코드 개발이 시작된 2026-11-04 이후만 기록한다. 그 이전 설계·ERD·발표자료 제작은 포함하지 않는다. 선택지 표는 회고 비교이며 당시 모두 실험했다는 뜻이 아니다. 기존 일지를 덮어쓰지 않고 누락을 보완한다.

## 문제점
기존 #34 일지는 개발환경 구축을 기록했지만, 11월 6일 실제로 수정한 의존성·브라우저 요청·본문 크기·컨테이너 권한 문제를 “의존성 정리”로만 요약해 구체적인 변경과 근거가 빠졌다.

## 원인
API 전이 의존성의 완전한 고정이 없었고 당시 Starlette 버전에 알려진 권고가 검출됐다. 브라우저 preflight 허용 항목이 부족했고 JSON 본문을 파싱하기 전 상한이 없었다. API 사용자 UID와 이미지 볼륨 권한·초기화 순서, 서비스 코드 복사 범위, 일부 서비스 로그 순환에도 보완이 필요했다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 의존성 강제 일괄 변경·상한 없는 요청 유지 | 설정 변경이 간단해 보임 | 프런트 호환성 손상과 과도한 입력 위험 | 미채택 |
| 서버 의존성 고정 + 경계별 제한·권한·회귀 검사 | 수정 이유와 검증 범위가 명확함 | 플랫폼별 별도 확인 필요 | 채택 |

## 해결 (적용 내용)
- API에 `requirements.lock`을 추가하고 FastAPI/Starlette 및 공통 runtime 잠금 의존성을 당시 검증된 조합으로 갱신했다.
- `RequestBodyLimit`으로 JSON 본문을 64 KiB로 제한했다. Content-Length가 없는 분할 전송도 합산해 초과하면 413으로 거절한다. 이후 이미지 업로드 정책까지 이 수치로 설명하지 않는다.
- 허용된 origin에 대한 POST/PATCH/DELETE 및 Authorization preflight를 보완했다. CORS를 인증 대체 수단으로 사용하지 않았다.
- API 실행 UID 10001, 이미지 초기화 완료 대기, API 사용자로 실제 볼륨 쓰기 검사를 추가했다. 서비스 디렉터리 전체를 이미지/개발 마운트에 반영했다.
- 누락된 로그 순환을 보완하고 up/check 기본 범위를 full에서 core로 줄였다. stop/status/logs의 전체 환경 대응은 유지했다.
- `kkulpick_backend_audit_2026-11-06.pdf` 13쪽 보고서로 구현·검증·미완료를 구분했다. 과거의 근거 없는 전체 완료율 수치를 완료 근거로 재사용하지 않았다.

## 왜 그렇게 해결했는지
백엔드 개발에 필요 없는 전체 스택을 기본으로 실행하지 않으면서, API가 실제로 사용하는 의존성과 입력 경계를 먼저 검증했다. 모바일 도구 의존성의 강제 버전 변경은 호환성 확인 없이 적용하지 않았다.

## 검증
- 당시 감사 보고서 6~7·11쪽: 도구 6개 + CI 실행 도구 9개 + API 계약/서비스 틀 14개 = 로컬 29개 통과 기록. 첫 수집 오류 후 올바른 PYTHONPATH로 수행한 결과다. DB 통합 검사 수치와 합산하지 않는다.
- 원격 `0c2bff5`의 5개 Actions가 성공했음을 이번 재검토에서 재확인했다: [접속 검사](https://github.com/daon217/swproject/actions/runs/42165837283), [API](https://github.com/daon217/swproject/actions/runs/42165837309), [전체 환경](https://github.com/daon217/swproject/actions/runs/42165837293), [DB](https://github.com/daon217/swproject/actions/runs/42165837322), [팀 빌드](https://github.com/daon217/swproject/actions/runs/42165837346).
- 고정 코드의 `test_contract.py`에는 preflight, 허용되지 않은 origin, Content-Length 유무별 과대 본문, 정상 JSON 보존 검사가 있다.
- 당시 API 20개·공통 runtime 39개 잠금 의존성의 알려진 권고 0건은 **당시 스캔 결과**다. 현재 보안 상태를 새로 점검한 수치가 아니다.

이번 보완에서는 과거 서비스 테스트를 재실행하지 않았다. 고정 커밋의 코드·기록·참조를 대조했으며 아래 한계를 포함한다.

## 남은 과제 / 주의
- 그때의 컨테이너/DB 검증은 GitHub Actions 근거이며 모든 팀원 PC·모바일 실기기·운영 장애 복구를 검증한 것은 아니다.
- 당시 모바일 의존성 경고는 남아 있었다. 이 문서가 최신 취약점 유무나 운영 보안 인증을 제공하지 않는다.
- 실제 OCR·모델 처리, 사용자 기능은 이 커밋에서 완성되지 않았다. 후속 #36/#42/#43을 함께 읽는다.
