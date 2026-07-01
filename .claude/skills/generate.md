---
name: generate
description: 유사 TOP3·CTR 범위 계산 + 진단 리포트 생성 (Basic/Standard/Challenge 분기)
---

# /generate — 진단 리포트 생성

`/insight`의 유사도 기준·패턴으로, 신규 5건을 진단하고 `output/content_prediction_report.md`를 생성하라.

## 공통 (Basic 필수)
신규 콘텐츠 1건당:
1. **유사 콘텐츠 TOP3** 계산 (Python 권장): 유사도 점수 → CTR 정렬 → 상위 3개 추출
2. **예상 CTR 범위**: 유사 TOP3의 CTR 최소~최대 (예 "3.0%~4.5%") + 근거 1줄
3. **유사 TOP3 비교표**: 제목 · CTR · 인게이지먼트율
4. **개선 제안 2가지**: 과거 패턴 기반, "이 요소를 바꾸면 CTR이 X%p 다름" 형태(감 금지)

> Python은 유사도·정렬·범위 계산을 담당하고, Claude는 수치를 마케터 언어로 해석해 개선 제안을 작성한다.

### Basic 리포트 구조
- 데이터 개요(정제 내용 포함) → 신규 5건 각 진단(범위·비교표·제안) → 종합 코멘트

## 🟡 Standard 추가
- 새 `new_content_info.csv`를 넣어도 동일 품질로 도는 **재현 파이프라인**(스크립트/명령) 제공
- 5건 일괄 진단 + 진단 리포트 섹션·지표를 본인이 설계한 근거 설명 (마케팅팀 관점)

## 🔴 Challenge 추가
- 진단 결과를 모아 **콘텐츠 발행 전략 기획안 1~2건** 생성
  - 문제 정의 / 근거 데이터 / 전략 제안 / 우선순위(점수·근거)
- 기획안 양식과 우선순위 판단 기준을 본인이 설계

## 출력
- `output/content_prediction_report.md` 생성
- 다음 단계 안내: `/review` 로 제출 전 자가 점검
