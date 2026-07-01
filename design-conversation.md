# [10] 마케팅 공통 문제 설계 대화 기록

> AX 해커톤 Problem 10 설계 과정에서 나눈 주요 프롬프트와 결정 사항을 정리한 문서입니다.
> 작성: 정혜인 | 날짜: 2026-07-01

---

## 1. 결과물 임팩트 논의

### Q. output이 약하다는 고민 — 구체화 또는 대안 아이디어?

**현황 문제**: "콘텐츠 성과 예측"이 자칫 ML 모델 과제로 오해되거나, 1회성 진단 문서로 끝나 AI 활용 역량이 잘 드러나지 않음.

**브레인스토밍 결과 — 세 가지 방향 검토**

| 옵션 | 설명 | 결론 |
|------|------|------|
| A. ML 회귀 예측 모델 | 70행으로 CTR 회귀/분류 모델 학습 → 예측값 출력 | **제외 범위** (70행은 과적합·신뢰구간 과대로 불가) |
| B. 패턴 기반 진단 (유사 TOP3) | Python으로 유사 콘텐츠 찾고 실제 성과로 기대 범위 제시 + Claude 해석 | **Basic 핵심**으로 채택 |
| C. 발행 전략 기획 자동화 | 진단 누적 → 데이터 기반 콘텐츠 발행 전략 기획안 | Challenge 레벨로 포함 |

**핵심 조정**: "예측 모델"이 아니라 "**과거 패턴 기반 진단·제안**"으로 프레이밍. Python(유사도·정렬) + Claude(해석·제안)의 역할 분담을 명확히 함.

---

## 2. 레벨 구조 설계

### Q. 현재 목표를 레벨 1로 하고 레벨 2, 3을 설정한다면?

**설계 원칙**: "1회성 진단" → "새 입력에도 도는 재현 파이프라인" → "데이터→전략 기획"으로 발전하는 누적형 구조. 페르소나 사다리: 마케터 → 그로스 마케터 → 마케팅 전략가.

### 최종 확정 레벨

```
🟢 Basic (100점)  — 마케터 수준
  → 신규 5건 각각: 예상 CTR 범위 + 유사 TOP3 비교표 + 개선 제안 2가지
  → content_prediction_report.md (또는 노션/구글 독스 공개 링크)

🟡 Standard (+30점, 누적 130점)  — 그로스 마케터 수준
  → Basic + 재사용 가능한 파이프라인
  → 새 new_content_info.csv 넣으면 유사 매칭→범위→제안→리포트 자동 생성 (/명령 또는 스크립트)
  → 진단 리포트 섹션·지표·유사도 기준을 본인이 직접 설계

🔴 Challenge (+30점, 누적 160점)  — 마케팅 전략가 수준
  → Standard + 진단 패턴에서 콘텐츠 발행 전략 기획안 자동 생성
  → 기획안 구성: 문제 정의 / 근거 데이터 / 전략 제안 / 우선순위
  → 기획안 양식·우선순위 기준도 본인이 설계
```

---

## 3. CSV 데이터 설계

### Q. 기존 problem-10-marketing-predictor 폴더와 노션 v2 정합성 맞추기

기존 소스 폴더에는 `company-info.md`만 존재했고(데이터 파일 없음), 그 company-info는 **구버전 스키마**(좋아요/공유, 이미지수, 정보성/이벤트/후기/브랜딩, 카카오/이메일 채널)를 전제하고 있었음. 노션 v2 권위 스펙은 **신버전 스키마**를 명시 → 신버전 기준으로 데이터 신규 설계 + company-info도 신버전 스키마에 맞춰 재작성.

**변경 전 컬럼 가정** (구버전 company-info 기준)
```
좋아요수, 공유수, 참여율, image_count, type(정보성/이벤트/후기/브랜딩), channel(블로그/인스타/유튜브/카카오/이메일)
```

**변경 후 컬럼** (노션 v2 기준 — past_content_performance.csv, 70행)
```
content_id, title, type, topic_category, channel, ctr, engagement_rate, reach, headline_length, has_emoji, posting_hour
```

**주요 변경 사항**
- `좋아요수/공유수` → `engagement_rate`(인게이지먼트율) 단일 지표로 정리
- `image_count` 제거, `headline_length`·`has_emoji`·`posting_hour` 추가 (입력 가능한 메타데이터 중심)
- `type` 값 변경: 정보성/이벤트/후기/브랜딩 → **카드뉴스/숏폼/블로그/인포그래픽** (포맷 기준)
- `topic_category` 신설: 생산성/커리어/트렌드/후기
- `channel` 축소: 카카오·이메일 제거 → **인스타그램/블로그/유튜브**
- 신규 콘텐츠 파일 `new_content_info.csv`(5행) 신설 — 성과 컬럼(ctr/engagement/reach) 없음 = 진단 대상

**의도적으로 심은 성과 패턴** (참여자가 발견·검증해야 할 신호)
- 숏폼+유튜브/인스타 + posting_hour 20 + has_emoji=True → CTR 최상위 구간(4.5~5.8%)
- 카드뉴스+인스타그램 + 저녁(18~20) + 이모지 → 강세 구간(3.7~4.5%)
- 블로그 + 아침(8) + no emoji + 긴 제목(30자+) → 저CTR 구간(1.4~1.8%)이나 후기·커리어는 인게이지먼트 상대적 양호
- posting_hour 18·20 > 12 > 8 (시간대 가산), has_emoji가 소셜 CTR 견인
- new 5건은 각각 past의 HIGH/STRONG/LOW/인포그래픽/개선여지 구간과 매칭되도록 설계

**의도적 데이터 품질 이슈 (참여자가 처리해야 할 과제)**
- 결측 2건: `C069` engagement_rate 빈 셀 / `C070` reach 빈 셀
- 완전 중복 행 1건: `content_id C003` 이 동일 값으로 2번 등장 (파일 마지막 행) → 제거 시 69건
- `has_emoji` 가 `True`/`False` **문자열** — 불리언 변환 처리 필요

---

## 4. Output 형식 결정

### Q. md 파일이면 안 됨 — 시각적으로 확인할 수 있어야 함

**결론**: 제출물은 `content_prediction_report.md`가 기본이되, 레벨별 HTML 샘플로 시각적 완성 예시 제공.

| 파일 | 주요 시각 요소 |
|------|---------------|
| `output/sample-basic.html` | 신규 콘텐츠 카드 + 예상 CTR 게이지 + 유사 TOP3 비교표 + 개선 제안 카드 |
| `output/sample-standard.html` | 파이프라인 플로우 다이어그램 + 5건 일괄 진단 대시보드 + 유사도 점수 막대 |
| `output/sample-challenge.html` | 우선순위 점수 계산기 + 발행 전략 기획안 P0/P1 카드 + 콘텐츠 캘린더 권고 |

---

## 5. 최종 파일 구조

```
[10] 마케팅 공통/
├── CLAUDE.md                  ← 참여자용 가이드 (레벨 구조 + 채점 + 제약)
├── problem.md                 ← 문제 명세
├── decisions.md               ← 의사결정 로그 템플릿
├── design-conversation.md     ← 이 파일 (설계 과정 기록)
├── data/
│   ├── past_content_performance.csv  ← 70행 (중복 1건·결측 2건 포함, 11컬럼)
│   └── new_content_info.csv          ← 5행 (예측 대상, 7컬럼)
├── context/
│   ├── company-info.md        ← 콘텐츠 성과 예측 도메인 지식
│   └── industry-news.md       ← 콘텐츠 마케팅·성과 예측 트렌드
├── .claude/skills/
│   ├── analyze.md             ← /analyze 슬래시 커맨드
│   ├── insight.md             ← /insight 슬래시 커맨드
│   ├── generate.md            ← /generate 슬래시 커맨드 (Basic/Standard/Challenge 분기)
│   └── review.md              ← /review 자가 채점 체크리스트
└── output/
    ├── template.md            ← 참여자용 빈칸 채우기 양식
    ├── sample-basic.html      ← Basic 완성 샘플 (브라우저에서 열기)
    ├── sample-standard.html   ← Standard 완성 샘플
    └── sample-challenge.html  ← Challenge 완성 샘플
```

---

## 6. 채점 기준 요약

| 레벨 | 항목 | 배점 |
|------|------|------|
| 🟢 Basic | 예상 CTR 범위 (5건) | 35점 |
| | 유사 콘텐츠 TOP3 비교표 | 30점 |
| | 개선 제안 2가지 (데이터 근거) | 25점 |
| | 제출 형식 (md/공개 링크) | 10점 |
| **Basic 합계** | | **100점** |
| 🟡 Standard | 파이프라인 재현성 | +15점 |
| | 진단 리포트 설계 (본인 기획) | +15점 |
| **Standard 합계** | | **130점** |
| 🔴 Challenge | 발행 전략 기획안 실효성 | +20점 |
| | 양식·우선순위 설계 (본인 기획) | +10점 |
| **Challenge 합계** | | **160점** |

> 최소 합격선: Basic 60점 (5건 CTR 범위 + 유사 TOP3 비교표 완성)

---

## 7. 제외 범위 (참여자 안내 필요)

- **ML 예측 모델 구현** (회귀·분류·신경망 — 70행으론 불가)
- 실시간 SNS 데이터 수집·크롤링
- 이미지·영상 자체 분석 (썸네일·영상 화질 등)
- 자동 발행 연동 (예약 게시·API 연동)
- 실제 기업 성과 데이터 (제공된 CSV 2종만 사용)
- 대시보드·웹 UI 구현
