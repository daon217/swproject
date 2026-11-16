# 모바일 앱

WBS 담당: 배정 필요 (프론트 초기 구현: 서지웅)

Expo SDK 58 + React Native 0.88 + Expo Router + TypeScript. 백엔드가 준비되기 전까지는 앱 안 목업 API로 동작한다.

## 실행
```bash
cd apps/mobile
npm install
npx expo run:android      # 개발 빌드(네이티브 모듈 포함). Expo Go만으로는 view-shot 캡처가 제한될 수 있음
npx expo start            # 개발 서버
npm run typecheck
npm run preview:web       # 웹 미리보기 http://localhost:8081 (화면 확인용)
```
웹 미리보기는 WebView 대신 iframe(`src/ui/WebPage.web.tsx`)을 쓰고 화면 캡처 없이 주소 기준 목업으로 분석한다. 많은 쇼핑몰이 iframe 표시를 막아 빈 화면일 수 있다. 실제 동작 확인은 기기·에뮬레이터에서 한다.

## 환경변수
`.env.example` 참고. `EXPO_PUBLIC_API_BASE_URL`이 비어 있으면 `src/shared/api/mock.ts`(목업), 값이 있으면 `src/shared/api/http.ts`가 기술 명세서 17장 경로로 호출한다.

## 구조
| 경로 | 역할 |
| --- | --- |
| `src/app/(tabs)` | 하단 탭: 최근(`recent`) · 브라우저(`index`, 첫 화면) · 설정(`settings`) |
| `src/app/*.tsx` | 로그인·가입·약관 원문·마이페이지·개인정보 수정·비밀번호 변경·고객지원·재료 필터·프리미엄·결제·결제 완료 |
| `src/usePageAnalysis.ts` | 앱 안 브라우저 페이지 캡처(react-native-view-shot) → `POST /analyses` → 폴링. URL·page_revision이 바뀌면 이전 결과 폐기 |
| `src/ui` | 플로팅(축소/확장/닫기), 결과 화면, 바로가기 홈, 공용 컴포넌트 |
| `src/shared` | API·타입·포맷 등. **확장(`apps/extension/src/shared`)에서 복사한 코드**이며 저장소(AsyncStorage)와 UUID·해시(expo-crypto)만 다르다. 공용 패키지로 묶는 것은 후속 작업 |

## Figma 대비 반영한 변경(2026-11-16 합의)
- Android 화면 캡처 보안 정책 때문에 다른 앱 위 오버레이 대신 **앱 안 브라우저**에서 쇼핑하고 그 화면만 캡처한다. 적용 앱 선택·오버레이 권한 화면 없음.
- 상품/식품 모드 선택 없음(서버 판별). 바로가기는 이 기기에만 저장(브라우저 시작 화면).
- 연령 → 생년월일, 가입 화면 `[필수] 개인정보 수집 및 이용 동의` + `원문보기 >`(`/terms`).
- 최저가 구역 없음, 중고 추천은 AI 추천 아래, 추천 피드백 제거, 비회원 기록 삭제 숨김.
- 결제는 VAN/PG 연결 없이 수단 선택 → 완료/오류 흐름만.

## 미검증
- 실제 기기·에뮬레이터에서 실행하지 않았다. `tsc --noEmit`, `expo-doctor`, `expo export --platform android`(번들 생성)까지만 확인했다.
- WebView 캡처(react-native-view-shot)는 기기에서 동작 확인이 필요하다.
