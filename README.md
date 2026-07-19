# ReadIT

## BCDS 투자유치 랜딩페이지

`index.html` — BCDS 투자유치(IR)용 원페이지 랜딩입니다.

- **디자인**: 화이트 베이스 + 레드 포인트, 심플 & 모던, 리퀴드 글래스(글래스모피즘)
- **텍스트/폰트**: 영어 카피, Inter 폰트 통일 (Google Fonts, 미로드 시 시스템 폰트 폴백)
- **3D**: 외부 라이브러리 없이 순수 WebGL 셰이더로 구현한 리퀴드 글래스 블롭 (마우스 인터랙션 반응)
- **인터랙션**: 스크롤 리빌, 3D 틸트 카드, 마그네틱 버튼, 커스텀 커서
- **반응형**: 모바일/태블릿/데스크톱 대응, `prefers-reduced-motion` 지원

### 페이지 구성

히어로(제품 대시보드 목업) → 기능 6종 → 작동 방식 3단계 → 제품 상세(대시보드/자동화
플로우 목업) → 보안 → FAQ 아코디언 → 문의 폼 → 푸터.

### 콘텐츠 상태

제품 카피는 **일러스트용 샘플**입니다(구체적 수치·고객 수·인증 주장은 넣지 않음).
실제 제품 정보로 교체 후 사용하세요. 목업 화면은 전부 CSS/SVG 스켈레톤이라 실제
수치를 표시하지 않습니다.

### 연락처 / 문의 폼

- 연락처: **010.8623.3425 / smilesean41@gmail.com** (Contact 섹션·푸터에 표시)
- 문의 폼은 **mailto 방식**입니다. 제출 시 방문자의 메일 앱이 열리고 폼 내용이
  자동으로 채워진 메일이 작성됩니다(수신자: smilesean41@gmail.com). 별도 백엔드가
  없으므로 방문자 기기에 메일 앱이 설정되어 있어야 합니다. 수신 주소는
  `assets/js/main.js`의 `CONTACT_EMAIL`에서 변경할 수 있습니다.

### GitHub Pages 배포

`.github/workflows/deploy-pages.yml`이 main 브랜치 푸시(또는 Actions 탭에서 수동 실행)
시 사이트를 GitHub Pages로 배포합니다.

1. **최초 1회**: 저장소 Settings → Pages → Source를 **GitHub Actions**로 설정
2. PR을 main에 머지하면 자동 배포
3. 배포 주소: `https://seungjelee41.github.io/ReadIT/`

### 실행

```bash
# 브라우저에서 index.html을 바로 열거나
python3 -m http.server 8000  # http://localhost:8000
```
