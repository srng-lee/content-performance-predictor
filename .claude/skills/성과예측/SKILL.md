---
name: 성과예측
description: new_content_info.csv를 받아 predict_pipeline.py를 실행해 유사 TOP3·예상 CTR 범위·개선 제안이 담긴 content_prediction_report.md를 자동 생성
---

# /성과예측 — 콘텐츠 성과 예측 파이프라인

신규 콘텐츠 정보(csv)를 받아 과거 성과 데이터 패턴으로 진단 리포트를 자동 생성한다.
계산(유사도·정렬·집계)은 전부 `predict_pipeline.py`가 담당하고, 이 스킬은 그 스크립트를 실행하는 역할만 한다.

## 입력
- (선택) 신규 콘텐츠 csv 경로 — 컬럼: `title, type, topic_category, channel, headline_length, has_emoji, posting_hour`
- (선택) 과거 성과 csv 경로 — 컬럼: `content_id, title, type, topic_category, channel, ctr, engagement_rate, reach, headline_length, has_emoji, posting_hour`
- 인자를 생략하면 기본값 사용: `data/new_content_info.csv`, `data/past_content_performance.csv`

## 처리
1. 과거 데이터 정제: 완전 중복 제거, engagement_rate·reach 결측을 컬럼 평균으로 대체, has_emoji 문자열→불리언 변환
2. 채널·유형·시간대·이모지·주제별 CTR/인게이지먼트 집계
3. 신규 콘텐츠별 유사 TOP3 계산: type·channel 일치(하드 필터) → topic_category(+4)·has_emoji(+2)·posting_hour(+1) 가중 점수 → 동점 시 headline_length 차이 작은 순
4. TOP3 CTR 최소~최대로 예상 CTR 범위 산출
5. 채널 단위 집계에서 개선 여지가 큰 순으로 개선 제안 2가지 자동 선정 (감·하드코딩 없이 수치 기반)

## 실행 방법
```
python predict_pipeline.py [new_csv_path] [past_csv_path] [output_path]
```
- 예: 기본 경로로 실행
  ```
  python predict_pipeline.py
  ```
- 예: 새 신규 콘텐츠 csv로 재현
  ```
  python predict_pipeline.py data/new_content_info_v2.csv
  ```
- 실행 중 콘솔에 1단계(정제 결과·성과 패턴)와 2단계(하드 필터 통과 후보 수) 점검 로그가 출력된다.

## 출력
- `output/content_prediction_report.md` (또는 지정한 output_path)
  - 신규 콘텐츠 1건당: 조건 요약, 예상 CTR 범위(+근거), 유사 콘텐츠 TOP3 비교표(제목·CTR·인게이지먼트율·유사도 점수), 개선 제안 2가지(수치 근거 포함)

## 재현성 확인
새 `new_content_info.csv`를 넣고 다시 실행해도 위 1~5단계 로직이 그대로 재실행되어 동일한 품질의 리포트가 생성된다 (경로·컬럼 값 외에는 하드코딩된 항목 없음).
