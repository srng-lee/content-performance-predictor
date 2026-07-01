---
name: analyze
description: 콘텐츠 성과 데이터 파악 — 컬럼·결측·중복·성과 패턴 분포 점검
---

# /analyze — 데이터 파악

`data/past_content_performance.csv`(70행)와 `data/new_content_info.csv`(5행)를 읽고 다음을 점검·요약하라.

## 1. 구조 확인
- 두 파일의 컬럼·행수 출력 (past 70행 / new 5행)
- 각 컬럼의 값 종류: type(카드뉴스/숏폼/블로그/인포그래픽), topic_category(생산성/커리어/트렌드/후기), channel(인스타그램/블로그/유튜브), posting_hour(8/12/18/20), has_emoji(True/False)

## 2. 데이터 품질 점검 (정제 필요)
- **결측치**: 빈 셀 탐지 (힌트: engagement_rate·reach 컬럼)
- **완전 중복행**: content_id 기준 중복 탐지 (힌트: C003)
- **타입 함정**: has_emoji가 문자열 "True"/"False"임을 확인하고 불리언 처리 방침 정하기
- 발견한 이슈와 처리 방침을 decisions.md에 기록하라고 안내

## 3. 성과 패턴 분포 (진단 근거 탐색)
- posting_hour별 평균 CTR (8 vs 12 vs 18 vs 20)
- has_emoji True/False별 평균 CTR
- type × channel 조합별 평균 CTR (상위·하위 구간 파악)
- topic_category별 평균 engagement_rate

## 출력
- 표/요약으로 위 결과 제시
- "이 패턴이 신규 5건 진단에 어떻게 쓰일지" 1~2줄 코멘트
- 다음 단계 안내: `/insight` 로 유사도 기준 설계
