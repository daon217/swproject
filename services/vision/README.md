# 이미지 전처리·OCR

WBS 담당: 이다온

현재는 팀 코드 반입을 위한 영역만 준비된 상태입니다. 기능 구현·실행 환경은 아직 없습니다.
기존 코드는 기능 브랜치에서 이 경로에 반입하고, 의존성 명세·잠금 파일·실행 명령·환경변수 예시를 함께 추가하세요.
상위 CONTRIBUTING.md를 따르고, API 변경은 contracts와 관련 담당자에게 반영하세요.


## 공통 실행 틀
[전체 개발환경](../../docs/WORKSPACE.md)을 통해 devapp.py의 연결용 FastAPI와 전용 Celery 큐를 실행합니다. 실제 담당 기능은 아직 연결하지 않았으며 business_ready=false입니다.
