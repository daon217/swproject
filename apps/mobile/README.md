# 모바일 앱

담당: 배정 필요

[각자 PC 개발 안내](../../docs/LOCAL_DEVELOPMENT.md)를 따릅니다. 현재는 API 연결 확인용 시작 코드이며 실제 업무 화면/기능은 별도 구현합니다.

루트에서 init/core 실행 후 이 폴더에서 `npm ci`, `npm start`. `.env.local`은 Android 에뮬레이터에서 PC의 API에 연결하는 `http://10.0.2.2:8000`을 사용합니다. 실제 휴대폰 연결·캡처·오버레이는 별도 설정/구현입니다.
