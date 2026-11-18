# 사용자 웹

담당: 김호진

[각자 PC 개발 안내](../../docs/LOCAL_DEVELOPMENT.md)를 따릅니다. 현재는 API 연결 확인용 시작 코드이며 실제 업무 화면/기능은 별도 구현합니다.

저장소 루트에서 `py tools/workspace.py init`, `py tools/workspace.py up --scope core` 실행 후 이 폴더에서 `npm ci`, `npm run dev`. Node 버전은 루트 `.nvmrc`를 사용합니다.
기본 API는 `.env.local`의 `INTERNAL_API_URL=http://127.0.0.1:8000`입니다. 기존 터널 주소 18000은 필요할 때만 사용합니다.
