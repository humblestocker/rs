# 매매일지 자동화 도구 구축 (로컬 우선 MVP)

## 1) MVP 기능 명세서

### 목표
- 데일리 기준 포트폴리오 현황을 **One-page**로 자동 생성.
- 종목별 매매 히스토리를 바탕으로 **다음 액션 알림** 생성.

### 범위 (MVP)
1. **수동 입력 폼 대체 CLI**
   - 거래 이벤트(BUY/SELL) 입력
   - 포지션 규칙(유닛/목표투입금/손절률/분할계획) 저장
   - 진입 근거/감정/회고/스크린샷 링크 저장
2. **데일리 포트폴리오 스냅샷**
   - 종목별 평균단가, 잔량, 목표 대비 투입률
   - 실현손익/미실현손익(현재가 JSON 입력 시)
   - 손절가 자동 계산
3. **Next Step 알림**
   - 투입률 저조(<60%), 투입 완료(>=100%), 손절가 이탈 경고
4. **출력**
   - `DATA/daily_portfolio.md` 생성
   - 텔레그램 전송은 2차: 현재는 파일 출력 결과를 복사/붙여넣기

### 비범위 (2차)
- 텔레그램 Bot API 자동 전송
- Notion API 동기화
- 주간 PDF 자동 생성

---

## 2) 화면 흐름(입력→저장→분석→리포트)

1. **입력**
   - 사용자가 거래 직후 CLI 명령으로 입력 (`add`)
2. **저장**
   - 로컬 SQLite (`DATA/trading_journal.db`) 저장
3. **분석**
   - 종목별 포지션 집계 및 규칙 점검 (`snapshot`)
4. **리포트**
   - 마크다운 One-page 파일 생성 (`DATA/daily_portfolio.md`)
   - 필요 시 텔레그램에 수동 전송

---

## 3) 개발 우선순위 및 일정

### Week 1 (핵심)
1. 데이터 스키마 확정 (거래/규칙/메모)
2. 거래 입력 커맨드 구현
3. 스냅샷/알림 규칙 구현
4. 마크다운 리포트 생성

### Week 2 (안정화)
1. 입력 템플릿 배치파일 작성 (Windows 용)
2. 스냅샷 포맷 개선
3. 운영 가이드/백업 정책 정리
4. (선택) 텔레그램 자동 전송 PoC

---

## 4) 구현 코드

- 실행 스크립트: `tools/trading_journal_mvp.py`
- 로컬 DB: `DATA/trading_journal.db`
- 결과 리포트: `DATA/daily_portfolio.md`

### 주요 명령

```bash
python tools/trading_journal_mvp.py init
```

```bash
python tools/trading_journal_mvp.py add \
  --ticker 005930 --side BUY --price 75000 --qty 10 \
  --unit-target 5 --capital-target-krw 160000000 \
  --loss-cut-pct 10 --split-plan 5:3:2 \
  --rationale "20일선 지지 + 거래량 증가" \
  --emotion-note "성급함 경계" --review "초기 진입" \
  --screenshot-link "file:///C:/shots/005930.png"
```

```bash
python tools/trading_journal_mvp.py snapshot \
  --price-json DATA/latest_prices.json \
  --output DATA/daily_portfolio.md
```

`DATA/latest_prices.json` 예시:

```json
{
  "005930": 74200,
  "035420": 176500
}
```

---

## 5) 배포 방법 (Windows, 무료, 클라우드 미사용)

1. Python 3.10+ 설치
2. 저장소 clone
3. 아래 명령으로 초기화

```bash
python tools/trading_journal_mvp.py init
```

4. 바탕화면에 `.bat` 파일 2개 생성 권장
   - `add_trade.bat` : add 명령 템플릿
   - `daily_snapshot.bat` : snapshot 명령 실행

5. 매일 장 마감 후 `daily_snapshot.bat` 실행

---

## 6) 유지보수 가이드

1. **백업**
   - `DATA/trading_journal.db`를 주 1회 외장 저장소 백업
2. **데이터 품질**
   - 거래 입력 누락 방지를 위해 1일 1회 스냅샷 생성
3. **룰 튜닝**
   - 알림 기준(60%, 100%, 손절률) 월 1회 조정
4. **확장 로드맵**
   - 2차: 텔레그램 자동전송 + 노션 싱크(정책 허용 시)

