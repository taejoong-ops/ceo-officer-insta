# @ceo_officer.kr 카드뉴스 자동 게시

## 사용법
1. `posts/YYYY-MM-DD/` 폴더를 만들고 카드 이미지 `01.png` ~ `07.png`와 `caption.txt`를 넣어요.
2. GitHub에 올려요.
3. 그 날짜 **오전 7시 30분(한국시간)**에 캐러셀로 자동 게시돼요.
4. 게시가 끝나면 폴더는 `posts/done/`으로 옮겨지고, 결과는 `logs/publish-log.md`에 남아요.

## 규칙
- 이미지: 최대 10장, 가로:세로 비율 4:5 ~ 1.91:1 (1080x1350, 1080x1080 권장)
- 캡션: 최대 2200자, 해시태그 30개 이하
- 게시에 실패하면 GitHub가 이메일로 알려줘요.

## 수동 실행 / 점검
GitHub 저장소 → **Actions → 인스타 자동 게시 → Run workflow**
- `dry_run` 체크(기본값): 게시하지 않고 점검만 해요.
- 체크 해제: 실제로 게시해요.

## 안전장치
저장소 변수 `PUBLISH_ENABLED`가 `true`가 아니면, 예약 실행은 점검만 해요.
첫 게시를 확인한 뒤에 켜요. (Settings → Secrets and variables → Actions → Variables)

## 토큰
`IG_ACCESS_TOKEN`은 GitHub Secrets에만 저장해요. 코드에는 절대 넣지 않아요.
