# frontend/src

`src/`는 실제 프론트 애플리케이션 코드가 있는 폴더입니다.

## 하위 문서

- [components/README.md](components/README.md)
- [hooks/README.md](hooks/README.md)
- [types/README.md](types/README.md)
- [locales/README.md](locales/README.md)
- [test/README.md](test/README.md)
- [__tests__/README.md](__tests__/README.md)
- [assets/README.md](assets/README.md)

## 주요 파일

- [main.tsx](main.tsx): React mount
- [App.tsx](App.tsx): 앱 orchestration (`channelAction`이 `action_index`+`canonical_id`를 페이로드로 묶음)
- [App.css](App.css), [index.css](index.css): 글로벌 스타일
- [i18n.ts](i18n.ts): 다국어 초기화
- [config.ts](config.ts): API base URL 등 런타임 설정
- [googleOAuth.ts](googleOAuth.ts): Google OAuth helper
- [utils/turnFocus.ts](utils/turnFocus.ts): 내 턴 진입 시 포커스 유틸

## 데이터 흐름

1. `App.tsx`가 인증/방/게임 screen 상태를 보유합니다.
2. `hooks/`가 auth bootstrap과 WebSocket lifecycle을 관리합니다.
3. `components/`가 화면과 도메인 UI를 조합합니다.
4. `types/`가 backend serializer shape를 TypeScript로 고정합니다.

## 의존성

- 상위 문서: [../README.md](../README.md)
- backend contract: [../../backend/app/services/state_serializer.py](../../backend/app/services/state_serializer.py)
