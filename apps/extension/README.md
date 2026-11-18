# Chrome 확장

> 최신 실제 API 연결·Docker UI 실행은 [프론트 · 백엔드 통합 실행](../../docs/FRONTEND_INTEGRATION.md)을 따릅니다. 기본 API는 실제 로컬 백엔드이며 화면 목업은 명시적으로 선택합니다.

WBS 담당: 서지웅

Chrome MV3 확장 프론트엔드. React 18 + TypeScript + Vite. 실제 로컬 백엔드 API를 기본으로 사용한다.

## 실행
```bash
cd apps/extension
npm install
npm run build          # 타입 검사 + dist/ 생성
```
Chrome `chrome://extensions` → 개발자 모드 → "압축해제된 확장 프로그램을 로드합니다" → `apps/extension/dist` 선택. Chrome 116 이상.

확장 설치 없이 화면만 보려면:
```bash
npm run preview:sidepanel   # http://localhost:5174/preview.html
```
`?url=` 로 분석할 페이지를 바꾼다(프린터 상품 / 땅콩 식품 / 상품 아님 링크가 화면에 있음). 미리보기는 localStorage를 쓴다.

## 환경변수
`.env.example` 참고. `VITE_API_BASE_URL`은 실제 API 주소이며 기본값은 `http://127.0.0.1:8000`이다. `VITE_USE_MOCK_API=true`를 명시했을 때만 `src/shared/api/mock.ts`를 사용한다. API 응답을 받지 못해도 목업으로 자동 전환하지 않는다.

## 구조
| 경로 | 역할 |
| --- | --- |
| `src/background` | 탭 URL 변경 감지 → 디바운스 → 활성 화면 캡처 → `POST /analyses` → 결과 폴링. 탭·URL·page_revision이 바뀌면 이전 결과 폐기 |
| `src/content` | 쇼핑몰 페이지 인페이지 플로팅 카드(누르면 사이드 패널 열기, 닫기). Shadow DOM으로 사이트 CSS와 분리 |
| `src/sidepanel` | 사이드 패널: AI 추천·최근·바로가기·설정 탭, 로그인·가입·마이페이지·개인정보 수정·비밀번호 변경·고객지원·재료 필터·프리미엄·결제 |
| `src/shared` | API 클라이언트(목업/HTTP), 타입, 결과 화면 공용 컴포넌트, 스타일 |

## Figma 대비 반영한 변경(2026-11-16 합의)
- 쇼핑몰 페이지에는 작은 플로팅 카드만 표시하고(닫기 가능), 카드를 누르면 사이드 패널의 AI 추천 탭이 열린다. 페이지 안에서 패널을 펼치지 않는다.
- 상품/식품 모드 선택 없음(서버가 판별).
- 바로가기는 이 기기(chrome.storage.local)에만 저장.
- 가입·개인정보 수정의 "연령" → 생년월일(만 나이는 Asia/Seoul 기준 계산, 마이페이지는 연령대 표시).
- 가입 화면에 `[필수] 개인정보 수집 및 이용 동의` + `원문보기 >` 추가(원문: `src/shared/terms.ts`, 법무 검토 전 초안).
- 최저가 구역 없음. 중고 추천은 AI 추천 아래. 추천 피드백(👍/👎) 제거.
- 비회원에게는 추천 기록 삭제를 보여주지 않음. 비회원이 중고 토글을 누르면 로그인 화면으로 이동.
- 결제는 실제 VAN/PG 연결 없이 수단 선택 → 결과(완료/오류) 흐름만 구현. 완료 여부는 구독 조회로 확정.

## 목업 데이터 확인 팁
- 결제 실패 화면: 개발자 도구에서 `kp.mock.paymentFail` 값을 true로 저장(미리보기는 `localStorage.setItem('kp.mock.paymentFail','true')`).
- 목업 계정·기록은 `kp.mock.db` 키에 저장된다. 실제 개인정보를 넣지 않는다.

## 미검증
- 실제 Chrome에 설치해 쇼핑몰 페이지에서 캡처·플로팅·사이드 패널 열기까지는 확인하지 않았다(미리보기 화면에서만 확인).
- 실제 API 연결 검증 범위는 [통합 실행 문서](../../docs/FRONTEND_INTEGRATION.md)의 자동 검증과 GitHub Actions 결과를 확인한다.
