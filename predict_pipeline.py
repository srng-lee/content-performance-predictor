"""
콘텐츠 성과 예측 파이프라인
새 new_content_info.csv 경로를 인자로 받아 유사 TOP3 계산 + 진단 리포트를 자동 생성한다.

사용법:
    python predict_pipeline.py [new_csv_path] [past_csv_path] [output_path]
    (인자를 생략하면 프로젝트 기본 경로: data/new_content_info.csv, data/past_content_performance.csv,
     output/content_prediction_report.md 를 사용한다)
"""

import csv
import sys
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_NEW_PATH = os.path.join(BASE_DIR, "data", "new_content_info.csv")
DEFAULT_PAST_PATH = os.path.join(BASE_DIR, "data", "past_content_performance.csv")
DEFAULT_OUTPUT_PATH = os.path.join(BASE_DIR, "output", "content_prediction_report.md")

HOURS = (8, 12, 18, 20)
BLOG_HEADLINE_THRESHOLD = 30
LOW_CONFIDENCE_SCORE_THRESHOLD = 2  # 하드필터 통과 후보 중 이 점수 이상이 하나도 없으면 "약한 벤치마크"로 표시
SMALL_SAMPLE_THRESHOLD = 5  # 이 값 미만인 n은 "표본이 적어 참고용" 캡션을 붙임


def fmt_n(n):
    if n < SMALL_SAMPLE_THRESHOLD:
        return f"n={n}건, 표본이 적어 참고용"
    return f"n={n}건"


# ---------- 1단계: 데이터 정제 ----------

def load_past(past_path):
    with open(past_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows


def clean_past(rows):
    """완전 중복 제거 + 결측치 평균 대체 + has_emoji 불리언 변환"""
    seen = set()
    clean = []
    dup_ids = []
    for r in rows:
        if r["content_id"] in seen:
            dup_ids.append(r["content_id"])
            continue
        seen.add(r["content_id"])
        clean.append(dict(r))

    er_vals = [float(r["engagement_rate"]) for r in clean if r["engagement_rate"] != ""]
    reach_vals = [float(r["reach"]) for r in clean if r["reach"] != ""]
    er_mean = round(sum(er_vals) / len(er_vals), 2)
    reach_mean = round(sum(reach_vals) / len(reach_vals), 1)

    missing_log = []
    for r in clean:
        if r["engagement_rate"] == "":
            missing_log.append((r["content_id"], "engagement_rate", er_mean))
            r["engagement_rate"] = er_mean
        else:
            r["engagement_rate"] = float(r["engagement_rate"])
        if r["reach"] == "":
            missing_log.append((r["content_id"], "reach", reach_mean))
            r["reach"] = reach_mean
        else:
            r["reach"] = float(r["reach"])
        r["ctr"] = float(r["ctr"])
        r["has_emoji"] = r["has_emoji"].strip().lower() == "true"
        r["posting_hour"] = int(r["posting_hour"])
        r["headline_length"] = int(r["headline_length"])

    return clean, {"dup_ids": dup_ids, "missing": missing_log, "er_mean": er_mean, "reach_mean": reach_mean}


def load_new(new_path):
    with open(new_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["has_emoji"] = r["has_emoji"].strip().lower() == "true"
        r["posting_hour"] = int(r["posting_hour"])
        r["headline_length"] = int(r["headline_length"])
    return rows


def avg(vals):
    return sum(vals) / len(vals) if vals else None


def compute_aggregates(clean):
    """정제 데이터에서 채널·유형·시간대·이모지·주제별 CTR/인게이지먼트 집계"""
    hour_ctr = defaultdict(list)
    emoji_ctr = defaultdict(list)
    type_channel_ctr = defaultdict(list)
    channel_hour_ctr = defaultdict(list)
    channel_emoji_ctr = defaultdict(list)
    topic_engagement = defaultdict(list)

    for r in clean:
        hour_ctr[r["posting_hour"]].append(r["ctr"])
        emoji_ctr[r["has_emoji"]].append(r["ctr"])
        type_channel_ctr[(r["type"], r["channel"])].append(r["ctr"])
        channel_hour_ctr[(r["channel"], r["posting_hour"])].append(r["ctr"])
        channel_emoji_ctr[(r["channel"], r["has_emoji"])].append(r["ctr"])
        topic_engagement[r["topic_category"]].append(r["engagement_rate"])

    blog = [r for r in clean if r["channel"] == "블로그"]
    blog_short = [r["ctr"] for r in blog if r["headline_length"] < BLOG_HEADLINE_THRESHOLD]
    blog_long = [r["ctr"] for r in blog if r["headline_length"] >= BLOG_HEADLINE_THRESHOLD]

    return {
        "hour_ctr": {h: (avg(v), len(v)) for h, v in hour_ctr.items()},
        "emoji_ctr": {e: avg(v) for e, v in emoji_ctr.items()},
        "type_channel_ctr": {k: (avg(v), len(v)) for k, v in type_channel_ctr.items()},
        "channel_hour_ctr": {k: (avg(v), len(v)) for k, v in channel_hour_ctr.items()},
        "channel_emoji_ctr": {k: (avg(v), len(v)) for k, v in channel_emoji_ctr.items()},
        "topic_engagement": {k: avg(v) for k, v in topic_engagement.items()},
        "blog_headline_short": (avg(blog_short), len(blog_short)),
        "blog_headline_long": (avg(blog_long), len(blog_long)),
    }


# ---------- 2단계: 유사도 설계 ----------

def hard_filter_pool(item, clean):
    return [r for r in clean if r["type"] == item["type"] and r["channel"] == item["channel"]]


def similarity_score(candidate, item):
    score = 0
    if candidate["topic_category"] == item["topic_category"]:
        score += 4
    if candidate["has_emoji"] == item["has_emoji"]:
        score += 2
    if candidate["posting_hour"] == item["posting_hour"]:
        score += 1
    return score


def top3_similar(item, clean):
    pool = hard_filter_pool(item, clean)
    ranked = sorted(
        pool,
        key=lambda r: (-similarity_score(r, item), abs(r["headline_length"] - item["headline_length"])),
    )
    return pool, ranked[:3]


def assess_confidence(item, pool):
    """저신뢰 원인을 "후보 수 부족"과 "저유사도" 두 가지로 구분해서 판단한다.
    이 둘을 구분하지 않고 하나의 기준(qualified<3)으로 뭉치면, 후보가 2건뿐인데 그 2건이
    전부 고유사도(예: 2/2)인 경우까지 "저유사도로 채워짐"이라고 잘못 표시하는 문제가 생긴다.

    - reason="insufficient_pool": 하드필터 통과 후보 자체가 3건 미만이라 TOP3를 못 채움
      (후보 품질과 무관하게 과거 데이터에 이 조합이 드문 것이 원인)
    - reason="low_similarity": 후보는 3건 이상 있지만 유사도 LOW_CONFIDENCE_SCORE_THRESHOLD점
      이상인 후보가 1건 이하라 TOP3 중 상당수가 약한 매칭으로 채워짐
    - reason=None: 저신뢰 아님
    """
    qualified = [r for r in pool if similarity_score(r, item) >= LOW_CONFIDENCE_SCORE_THRESHOLD]
    pool_size = len(pool)
    qualified_count = len(qualified)

    if pool_size < 3:
        reason = "insufficient_pool"
    elif qualified_count <= 1:
        reason = "low_similarity"
    else:
        reason = None

    return {
        "is_low_confidence": reason is not None,
        "reason": reason,
        "qualified_count": qualified_count,
        "pool_size": pool_size,
    }


# ---------- 3단계: 개선 제안 ----------

def topic_engagement_within_pool(item, clean):
    """같은 type×channel 풀 내에서 topic_category별 engagement_rate 비교(더 세밀한 폴백 레버)"""
    pool = hard_filter_pool(item, clean)
    by_topic = defaultdict(list)
    for r in pool:
        by_topic[r["topic_category"]].append(r["engagement_rate"])
    return {k: (avg(v), len(v)) for k, v in by_topic.items() if v}


def _detail_candidates(item, agg):
    """posting_hour·has_emoji·headline_length 레버에서 실제 CTR 개선 여지가 있는 후보만 추출"""
    ch = item["channel"]
    candidates = []

    hour_opts = {h: v for h, v in
                 ((h, agg["channel_hour_ctr"].get((ch, h))) for h in HOURS) if v is not None}
    if hour_opts:
        best_hour = max(hour_opts, key=lambda h: hour_opts[h][0])
        cur_hour_stat = hour_opts.get(item["posting_hour"])
        if cur_hour_stat is not None and best_hour != item["posting_hour"]:
            best_ctr, best_n = hour_opts[best_hour]
            cur_ctr, cur_n = cur_hour_stat
            delta = best_ctr - cur_ctr
            if delta > 0:
                sentence = (
                    f"발행 시간을 {best_hour}시로 변경할 경우, 동일 채널({ch})의 {best_hour}시 평균 CTR은 "
                    f"{best_ctr:.2f}%({fmt_n(best_n)})로, 현재 {item['posting_hour']}시 평균 CTR "
                    f"{cur_ctr:.2f}%({fmt_n(cur_n)})보다 +{delta:.2f}%p 높습니다."
                )
                # 표본이 작은 상태에서, 채널 단위보다 넓은 전체 콘텐츠 기준 시간대 효과와 방향이
                # 엇갈리면(=이 조합에서만 보이는 우연한 패턴일 가능성) 참고용이라는 점을 명시한다.
                overall_best = agg["hour_ctr"].get(best_hour)
                overall_cur = agg["hour_ctr"].get(item["posting_hour"])
                if (min(best_n, cur_n) < SMALL_SAMPLE_THRESHOLD and overall_best and overall_cur
                        and overall_best[0] < overall_cur[0]):
                    sentence += (
                        f" 다만 전체 콘텐츠 기준으로는 오히려 {item['posting_hour']}시"
                        f"({overall_cur[0]:.2f}%)가 {best_hour}시({overall_best[0]:.2f}%)보다 높게 나타나 "
                        f"방향성이 엇갈리므로, 이 수치는 참고용으로만 활용하는 것이 안전합니다."
                    )
                candidates.append((delta, sentence))

    emo_true = agg["channel_emoji_ctr"].get((ch, True))
    emo_false = agg["channel_emoji_ctr"].get((ch, False))
    if not item["has_emoji"] and emo_true and emo_false:
        delta = emo_true[0] - emo_false[0]
        if delta > 0:
            candidates.append((delta, (
                f"제목에 이모지를 추가할 경우, 동일 채널({ch})의 이모지 포함 평균 CTR은 "
                f"{emo_true[0]:.2f}%({fmt_n(emo_true[1])})로, 미포함 평균 CTR {emo_false[0]:.2f}%({fmt_n(emo_false[1])})"
                f"보다 +{delta:.2f}%p 높습니다."
            )))

    if ch == "블로그" and item["headline_length"] >= BLOG_HEADLINE_THRESHOLD:
        short_avg, short_n = agg["blog_headline_short"]
        long_avg, long_n = agg["blog_headline_long"]
        if short_avg and long_avg:
            delta = short_avg - long_avg
            if delta > 0:
                candidates.append((delta, (
                    f"제목을 {BLOG_HEADLINE_THRESHOLD}자 미만으로 축약할 경우, 블로그 짧은 제목의 평균 CTR은 "
                    f"{short_avg:.2f}%({fmt_n(short_n)})로, {BLOG_HEADLINE_THRESHOLD}자 이상 제목의 평균 CTR "
                    f"{long_avg:.2f}%({fmt_n(long_n)})보다 +{delta:.2f}%p 높습니다."
                )))

    candidates.sort(key=lambda c: -c[0])
    return candidates


def second_best_combo(agg, cur_combo):
    """현재 조합을 제외한 type×channel 조합 중 평균 CTR이 가장 높은 조합(격차 근거용)"""
    combos = [(k, v) for k, v in agg["type_channel_ctr"].items() if k != cur_combo]
    return max(combos, key=lambda kv: kv[1][0])


def build_suggestions(item, agg, clean):
    detail_candidates = _detail_candidates(item, agg)

    cur_combo = (item["type"], item["channel"])
    best_combo = max(agg["type_channel_ctr"], key=lambda k: agg["type_channel_ctr"][k][0])
    cur_combo_ctr, cur_combo_n = agg["type_channel_ctr"].get(cur_combo, (None, 0))

    if cur_combo == best_combo:
        # 이미 최고 CTR 조합 -> 유지 권장(2위 조합과의 격차 명시) + 더 세밀한 레버 하나를 보충 제안으로 사용
        second_combo, (second_ctr, second_n) = second_best_combo(agg, cur_combo)
        gap = cur_combo_ctr - second_ctr
        result = [(
            f"현재 조합({item['type']}×{item['channel']})이 학습 데이터 내 최고 CTR 조합"
            f"({cur_combo_ctr:.2f}%, {fmt_n(cur_combo_n)})이며, 2위 조합({second_combo[0]}×{second_combo[1]}, "
            f"{second_ctr:.2f}%, {fmt_n(second_n)})보다 +{gap:.2f}%p 높습니다. 포맷·채널을 변경하기보다 "
            f"현재 조합을 유지하는 것을 권장합니다."
        )]
        if detail_candidates:
            result.append(detail_candidates[0][1])
        else:
            topic_avg = topic_engagement_within_pool(item, clean)
            cur_topic_stat = topic_avg.get(item["topic_category"])
            if topic_avg and cur_topic_stat is not None:
                best_topic = max(topic_avg, key=lambda t: topic_avg[t][0])
                if best_topic != item["topic_category"]:
                    best_er, best_n = topic_avg[best_topic]
                    cur_er, cur_n = cur_topic_stat
                    delta = best_er - cur_er
                    if delta > 0:
                        result.append((
                            f"참고로 동일 조합({item['type']}×{item['channel']}) 내에서 '{best_topic}' 주제의 "
                            f"평균 인게이지먼트율은 {best_er:.2f}%({fmt_n(best_n)})로, 현재 주제 "
                            f"'{item['topic_category']}'의 평균 {cur_er:.2f}%({fmt_n(cur_n)})보다 높습니다 — "
                            f"관련 스토리텔링 요소를 참고할 수 있습니다."
                        ))
        return result[:2]

    result = [c[1] for c in detail_candidates[:2]]
    if len(result) < 2 and cur_combo_ctr is not None:
        best_ctr, best_n = agg["type_channel_ctr"][best_combo]
        delta = best_ctr - cur_combo_ctr
        if delta > 0:
            result.append((
                f"참고로 {best_combo[0]}×{best_combo[1]} 조합의 평균 CTR은 {best_ctr:.2f}%({fmt_n(best_n)})로, "
                f"현재 조합({item['type']}×{item['channel']})의 평균 CTR {cur_combo_ctr:.2f}%({fmt_n(cur_combo_n)})"
                f"보다 +{delta:.2f}%p 높습니다. 다만 이는 발행 시간·이모지 조정과 달리 콘텐츠 형식 자체를 "
                f"바꿔야 하는 더 큰 변화이므로, 세부 조정을 먼저 적용해보고 그래도 개선이 부족할 때 장기 "
                f"검토 과제로 고려하는 것을 권장합니다."
            ))
    return result[:2]


# ---------- 콘솔 리포트 (1·2단계 점검용) ----------

def print_step1_summary(rows, clean, meta):
    print("=== [1단계] 데이터 정제 결과 ===")
    print(f"원본 {len(rows)}행 → 중복 제거 후 {len(clean)}행 (제거된 content_id: {meta['dup_ids']})")
    for cid, col, val in meta["missing"]:
        print(f"결측 대체: {cid}.{col} → {val} (결측 제외 평균)")
    print()


def print_step1_patterns(agg):
    print("=== [1단계] 성과 패턴 집계 ===")
    print("[시간대별 평균 CTR]")
    for h in HOURS:
        stat = agg["hour_ctr"].get(h)
        print(f"  {h}시: {stat[0]:.2f}%(n={stat[1]})" if stat is not None else f"  {h}시: 데이터 없음")

    print("[이모지별 평균 CTR]")
    for flag in (True, False):
        v = agg["emoji_ctr"].get(flag)
        print(f"  has_emoji={flag}: {v:.2f}%" if v is not None else f"  has_emoji={flag}: 데이터 없음")

    print("[유형×채널별 평균 CTR]")
    for k in sorted(agg["type_channel_ctr"], key=lambda k: -agg["type_channel_ctr"][k][0]):
        v, n = agg["type_channel_ctr"][k]
        print(f"  {k[0]}×{k[1]}: {v:.2f}% (n={n})")

    print("[주제별 평균 engagement_rate]")
    for k in sorted(agg["topic_engagement"], key=lambda k: -agg["topic_engagement"][k]):
        print(f"  {k}: {agg['topic_engagement'][k]:.2f}%")

    print("[블로그 제목 길이 효과]")
    short_avg, short_n = agg["blog_headline_short"]
    long_avg, long_n = agg["blog_headline_long"]
    print(f"  {BLOG_HEADLINE_THRESHOLD}자 미만: {short_avg:.2f}% (n={short_n})")
    print(f"  {BLOG_HEADLINE_THRESHOLD}자 이상: {long_avg:.2f}% (n={long_n})")
    print()


def print_step2_pool_check(new_rows, clean):
    print("=== [2단계] 하드 필터(type+channel) 통과 후보 수 ===")
    for item in new_rows:
        pool, _ = top3_similar(item, clean)
        status = "OK" if len(pool) >= 3 else "부족(3건 미만)"
        print(f"  '{item['title']}' ({item['type']}×{item['channel']}): {len(pool)}건 → {status}")
    print()


# ---------- 리포트 생성 ----------

def describe_match_axes(candidate, item):
    """두 콘텐츠가 주제·이모지·발행시간 중 무엇이 일치하는지 사람이 읽는 말로 설명"""
    matched = []
    if candidate["topic_category"] == item["topic_category"]:
        matched.append("주제")
    if candidate["has_emoji"] == item["has_emoji"]:
        matched.append("이모지 유무")
    if candidate["posting_hour"] == item["posting_hour"]:
        matched.append("발행 시간")
    if not matched:
        return "형식(유형·채널) 외에는 일치하는 조건이 없었으며"
    if len(matched) == 3:
        return "주제·이모지 유무·발행 시간까지 모두 일치했으며"
    return "·".join(matched) + "만 일치했으며"


def describe_engagement_pattern(top3):
    """TOP3의 CTR은 유사한데 인게이지먼트율은 차이나는 경우, 그 사실을 해석 문장으로 만든다.
    (CTR 스프레드가 작고 인게이지먼트율 스프레드가 상대적으로 큰 경우에만 등장 — 데이터에서 자동 판단)"""
    if len(top3) < 2:
        return None
    ctrs = [c["ctr"] for c in top3]
    ers = [c["engagement_rate"] for c in top3]
    ctr_spread = max(ctrs) - min(ctrs)
    er_spread = max(ers) - min(ers)
    if ctr_spread <= 0.7 and er_spread >= 0.5:
        return (
            f"위 콘텐츠들은 CTR이 {min(ctrs):.1f}~{max(ctrs):.1f}%로 큰 차이가 없었으나, 인게이지먼트율은 "
            f"{min(ers):.1f}~{max(ers):.1f}%로 콘텐츠별 편차가 있었습니다. 이는 클릭률은 유사했지만 저장·공감 "
            f"등 반응으로 이어진 정도는 콘텐츠마다 달랐음을 의미합니다."
        )
    return None


def build_highlight(item, pool, top3, agg, confidence):
    """이 콘텐츠에서 어떤 특별한 판단이 필요했는지를 (상황/근거/결론) 3줄로, 아직 안 나온 내용을
    미리 언급하지 않고 그 자체로 이해되는 말로 설명한다."""
    cur_combo = (item["type"], item["channel"])
    best_combo = max(agg["type_channel_ctr"], key=lambda k: agg["type_channel_ctr"][k][0])
    full_match = sum(1 for r in pool if similarity_score(r, item) == 7)

    if confidence["reason"] == "insufficient_pool":
        situation = f"이 조합과 동일한 과거 콘텐츠가 {confidence['pool_size']}건에 불과해, 비교 대상 자체가 부족했습니다."
        evidence = "이는 콘텐츠의 품질 문제가 아니라, 이 유형·채널 조합으로 과거에 발행된 콘텐츠 자체가 드물었기 때문입니다."
        conclusion = "따라서 아래 비교 결과는 참고용으로 활용하고, 발행 후 실제 성과를 반드시 확인해야 합니다."
    elif confidence["reason"] == "low_similarity":
        match_desc = describe_match_axes(top3[0], item) if top3 else "조건이 거의 일치하지 않았으며"
        situation = (
            f"형식이 유사한 과거 콘텐츠가 {confidence['pool_size']}건 있었으나, 그중 조건까지 실제로 유사하다고 "
            f"볼 수 있는 콘텐츠는 {confidence['qualified_count']}건에 불과했습니다."
        )
        evidence = f"가장 유사했던 콘텐츠({top3[0]['content_id']})조차 {match_desc}, 나머지 후보는 해당 조건마저 일치하지 않았습니다."
        conclusion = "따라서 아래 예상 범위는 참고용으로 활용하고, 발행 후 실제 성과를 반드시 확인해야 합니다."
    elif cur_combo == best_combo:
        combo_ctr, combo_n = agg["type_channel_ctr"][cur_combo]
        situation = f"이 콘텐츠는 {cur_combo[0]}×{cur_combo[1]} 형식이며, 이 조합은 과거 데이터 전체에서 CTR이 가장 높았던 조합입니다."
        evidence = f"{cur_combo[0]}×{cur_combo[1]} 콘텐츠(n={combo_n}건)의 평균 CTR은 {combo_ctr:.2f}%로, 다른 모든 형식·채널 조합보다 높았습니다."
        conclusion = "따라서 형식이나 채널 변경을 제안하기보다, 세부적인 조정에 초점을 맞췄습니다."
    elif item["channel"] == "블로그" and item["headline_length"] >= BLOG_HEADLINE_THRESHOLD:
        situation = (
            f"이 콘텐츠는 블로그 제목이 {item['headline_length']}자로, 과거 데이터에서 CTR이 하락하기 "
            f"시작하는 기준선({BLOG_HEADLINE_THRESHOLD}자)을 이미 초과한 상태입니다."
        )
        if confidence["qualified_count"] == len(pool):
            evidence = f"다만 형식(유형·채널)이 동일한 과거 콘텐츠 {len(pool)}건 모두 조건이 유사해 비교 근거는 충분했습니다."
        else:
            evidence = (
                f"다만 형식(유형·채널)이 동일한 과거 콘텐츠 {len(pool)}건 중 {confidence['qualified_count']}건은 "
                f"조건이 유사해 비교 근거는 충분했습니다."
            )
        conclusion = "따라서 유사 콘텐츠와의 비교 자체는 안정적으로 이루어졌으나, 제목 길이는 별도로 점검할 필요가 있었습니다."
    elif len(pool) < 10:
        situation = (
            f"이 콘텐츠와 형식(유형·채널)이 동일한 과거 콘텐츠는 {len(pool)}건으로, 다른 신규 콘텐츠들보다 "
            f"비교 대상의 폭이 좁은 편이었습니다."
        )
        if confidence["qualified_count"] == len(pool):
            evidence = (
                f"다만 {len(pool)}건 모두 조건이 유사했고, 그중 {full_match}건은 주제·이모지 유무·발행 "
                f"시간까지 모든 조건이 일치해 판단 근거로 충분했습니다."
            )
        else:
            evidence = (
                f"다만 그중 {confidence['qualified_count']}건은 조건이 유사했고, {full_match}건은 주제·이모지 "
                f"유무·발행 시간까지 모든 조건이 일치해 판단 근거로 충분했습니다."
            )
        conclusion = "따라서 후보 수는 적었으나 후보의 유사도가 높아, 다른 콘텐츠와 동일한 방식으로 비교하는 데 문제가 없었습니다."
    else:
        if full_match > 0:
            evidence = f"그중 {full_match}건은 주제·이모지 유무·발행 시간까지 모든 조건이 일치해 유사도가 매우 높았습니다."
        else:
            evidence = "주제·이모지 유무·발행 시간 중 여러 조건이 일치하는 콘텐츠가 다수 있었습니다."
        situation = (
            f"이 콘텐츠와 형식(유형·채널)이 동일한 과거 콘텐츠가 {len(pool)}건 있어, 비교 대상이 풍부한 "
            f"편이었습니다."
        )
        conclusion = "따라서 별도의 예외 처리 없이 표준 방식으로 비교해도 신뢰할 수 있는 결과를 얻었습니다."

    return situation, evidence, conclusion


def summarize_item(item, clean, agg):
    """전체 요약 표의 한 행(조건·예상 CTR·핵심 판단)을 데이터에서 도출"""
    pool, top3 = top3_similar(item, clean)
    confidence = assess_confidence(item, pool)
    ctrs = [c["ctr"] for c in top3]
    ctr_min, ctr_max = min(ctrs), max(ctrs)
    range_label = f"{ctr_min:.1f}~{ctr_max:.1f}%"
    if confidence["is_low_confidence"]:
        range_label += "(저신뢰)"

    cur_combo = (item["type"], item["channel"])
    best_combo = max(agg["type_channel_ctr"], key=lambda k: agg["type_channel_ctr"][k][0])

    if confidence["is_low_confidence"]:
        verdict = "벤치마크 부족, 모니터링 필요"
    elif cur_combo == best_combo:
        verdict = "이미 최적 조합, 유지 권장"
    else:
        suggestions = build_suggestions(item, agg, clean)
        first = suggestions[0] if suggestions else ""
        if "제목" in first and "축약" in first:
            verdict = "제목 축약 시 큰 개선 여지"
        elif "발행 시간" in first:
            verdict = "발행 시간 조정 시 개선 여지"
        elif "이모지" in first:
            verdict = "이모지 추가 시 개선 여지"
        elif first:
            verdict = "세부 조정 시 개선 여지"
        else:
            verdict = "특별한 개선 여지 없음"

    condition_label = f"{item['type']}·{item['channel']}·{item['posting_hour']}시"
    return condition_label, range_label, verdict


def render_report(new_rows, clean, agg, source_new_path, source_past_path):
    lines = []
    lines.append(f"# 콘텐츠 성과 예측 리포트")
    lines.append("")
    lines.append("## 우리가 해결해야 하는 문제")
    lines.append("")
    lines.append(
        "마케터는 콘텐츠를 발행하기 전 \"반응이 어떨까\"를 감(感)으로 판단하고, 발행 후에야 성과를 확인합니다. "
        "과거 데이터가 있어도 매번 수동으로 유사 콘텐츠를 찾아 비교하기는 번거롭습니다."
    )
    lines.append(
        f"이 리포트는 신규 콘텐츠 1건마다 과거 {len(clean)}건 중 조건이 가장 유사한 콘텐츠 TOP3를 자동으로 찾아, "
        "그 실제 CTR을 근거로 발행 전 예상 범위를 제시합니다."
    )
    lines.append(
        "유사도는 먼저 콘텐츠 유형(type)과 채널(channel)이 완전히 동일한 콘텐츠만 후보로 선별한 뒤, 그중 "
        "주제·이모지 유무·발행 시간이 일치하는 정도에 따라 순위를 매겨 판단합니다(자세한 가중치는 아래 "
        "'유사도 기준' 참고)."
    )
    lines.append("")
    lines.append("> 📖 **용어 설명**")
    lines.append("> - CTR(클릭률): 콘텐츠를 본 사람 중 실제로 클릭한 비율(%)")
    lines.append("> - 인게이지먼트율: 좋아요·댓글·공유 등 반응한 비율(%)")
    lines.append("> - %p(퍼센트포인트): \"3%→5%\"의 차이는 \"2%p\"로 표기합니다(2% 증가와는 다른 개념입니다)")
    lines.append("> - content_id: 과거 성과 데이터의 콘텐츠 고유 번호(예: C066)")
    lines.append("> - n: 표본 개수(콘텐츠 건수)")
    lines.append("> - 하드필터/가중점수: 유사 콘텐츠를 찾는 기준(아래 '유사도 기준' 참고)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "아래 신규 콘텐츠 5건은 마케팅팀이 발행을 검토 중인 콘텐츠 후보이며, 아직 발행 전이라 실제 성과 "
        "데이터가 없습니다. 이 리포트는 발행 전 이 5건 각각의 예상 반응을 진단합니다."
    )
    lines.append("")
    lines.append(f"- 학습 대상: `{os.path.basename(source_past_path)}` ({len(clean)}건, 중복 제거 후)")
    lines.append(f"- 진단 대상: `{os.path.basename(source_new_path)}` ({len(new_rows)}건)")
    lines.append("- 데이터 정제: 완전 중복 1건 제거(69건 기준) / engagement_rate·reach 결측은 컬럼 평균 대체 / has_emoji 문자열→불리언 변환")
    lines.append("- 유사도 기준: type·channel 일치(하드 필터) → topic_category(+4)·has_emoji(+2)·posting_hour(+1) 가중 점수 → 동점 시 headline_length 차이 작은 순")
    lines.append("")
    lines.append("## 예상 CTR 범위 산출 방식")
    lines.append("")
    lines.append(
        f"이 리포트는 ML 예측 모델이 아닙니다. {len(clean)}건 규모의 적은 데이터로 특정 수치를 정확히 예측하는 "
        "것은 신뢰도가 낮으므로, 조건이 유사한 과거 콘텐츠의 실제 성과를 근거로 예상 범위를 제시하는 방식을 "
        "사용합니다."
    )
    lines.append("")
    lines.append("- 1단계: 조건이 가장 유사한 과거 콘텐츠 3건(TOP3)을 찾습니다")
    lines.append("- 2단계: 해당 3건의 실제 CTR을 확인합니다")
    lines.append("- 3단계: 최솟값~최댓값을 예상 범위로 제시합니다")
    lines.append("")
    lines.append(
        "TOP3에 유사도가 낮은 콘텐츠가 포함되면 CTR 범위가 넓어지며 신뢰도가 낮아집니다. 이 경우 범위 앞에 "
        "\"신뢰도 낮음\"을 표기해 해당 수치를 참고용으로만 활용하도록 안내합니다."
    )
    lines.append("")
    lines.append("## 개선 제안 산출 방식")
    lines.append("")
    lines.append(
        "개선 제안은 기본적으로 \"현재보다 더 나은 형식이나 시간대·이모지 조합이 있는지\"를 과거 데이터에서 "
        "찾아 제시합니다. 다만 현재 형식·채널 조합이 이미 과거 데이터에서 가장 성과가 좋았던 조합이라면, "
        "인위적으로 다른 대안을 제시하기보다 \"현재 조합을 유지하는 것이 유리하다\"는 판단 자체를 하나의 "
        "제안으로 간주합니다. 이 경우 발행 시간, 이모지, 제목 길이 등 형식보다 세부적인 조정 요소 중 실제 "
        "개선 여지가 있는 항목을 찾아 나머지 제안으로 제시합니다."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 신규 콘텐츠 요약")
    lines.append("")
    lines.append("| 신규 콘텐츠 | 조건 | 예상 CTR | 핵심 판단 |")
    lines.append("|---|---|---|---|")
    for idx, item in enumerate(new_rows, start=1):
        condition_label, range_label, verdict = summarize_item(item, clean, agg)
        lines.append(f"| {idx}. {item['title']} | {condition_label} | {range_label} | {verdict} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    for idx, item in enumerate(new_rows, start=1):
        pool, top3 = top3_similar(item, clean)
        ctrs = [c["ctr"] for c in top3]
        ctr_min, ctr_max = min(ctrs), max(ctrs)
        suggestions = build_suggestions(item, agg, clean)
        confidence = assess_confidence(item, pool)

        situation, evidence, conclusion = build_highlight(item, pool, top3, agg, confidence)

        lines.append(f"## 신규 콘텐츠 {idx}: {item['title']}")
        lines.append("")
        lines.append("**이 콘텐츠의 특이점**")
        lines.append("")
        lines.append(f"- 📌 상황: {situation}")
        lines.append(f"- 🔍 근거: {evidence}")
        lines.append(f"- 📊 결론: {conclusion}")
        lines.append("")
        lines.append(
            f"- 조건: {item['type']} · {item['topic_category']} · {item['channel']} · "
            f"{item['posting_hour']}시 · 이모지 {'O' if item['has_emoji'] else 'X'} · 제목 {item['headline_length']}자"
        )
        lines.append(f"- 하드 필터(type×channel) 통과 후보: {len(pool)}건")
        lines.append("")
        lines.append("**유사 콘텐츠 TOP3 비교표**")
        lines.append("")
        lines.append("| 순위 | content_id | 제목 | CTR | 인게이지먼트율 | 유사도 점수 |")
        lines.append("|---|---|---|---|---|---|")
        for rank, c in enumerate(top3, start=1):
            score = similarity_score(c, item)
            lines.append(
                f"| {rank} | {c['content_id']} | {c['title']} | {c['ctr']:.1f}% | "
                f"{c['engagement_rate']:.1f}% | {score}/7 |"
            )
        lines.append("")
        lines.append("유사도 점수는 7점 만점(주제 일치 4점 + 이모지 일치 2점 + 시간대 일치 1점)입니다.")
        lines.append("")
        engagement_note = describe_engagement_pattern(top3)
        if engagement_note:
            lines.append(engagement_note)
            lines.append("")

        if confidence["reason"] == "insufficient_pool":
            lines.append(
                f"> ⚠️ **벤치마크 신뢰도 낮음**: 이 조합과 형식이 동일한 과거 콘텐츠가 {confidence['pool_size']}건에 "
                f"불과해 TOP3를 모두 채우지 못했습니다. 이는 콘텐츠의 품질 문제가 아니라 비교 대상 자체가 부족한 "
                f"것입니다. 위 표는 참고용이며, 발행 후 실제 성과를 반드시 확인해야 합니다."
            )
            lines.append("")
            lines.append(f"- **추정 CTR 범위(신뢰도 낮음): {ctr_min:.1f}% ~ {ctr_max:.1f}%**")
            lines.append(
                f"  - 근거: 비교 가능했던 {len(top3)}건({', '.join(c['content_id'] for c in top3)})의 실제 CTR 중 "
                f"최솟값과 최댓값입니다. 다만 비교 대상이 부족해 참고용으로만 활용해야 합니다."
            )
        elif confidence["reason"] == "low_similarity":
            lines.append(
                f"> ⚠️ **벤치마크 신뢰도 낮음**: 형식이 동일한 과거 콘텐츠 {confidence['pool_size']}건 중 조건까지 "
                f"실제로 유사한 콘텐츠는 {confidence['qualified_count']}건에 불과했습니다. 이에 따라 위 표에는 "
                f"조건이 크게 다른 콘텐츠도 참고용으로 포함했습니다 — 이 신규 콘텐츠는 과거 데이터에서 뚜렷한 "
                f"비교 대상을 찾기 어려운 경우에 해당합니다. 아래 범위는 참고용이며, 발행 후 실제 성과를 반드시 "
                f"확인해야 합니다."
            )
            lines.append("")
            lines.append(f"- **추정 CTR 범위(신뢰도 낮음): {ctr_min:.1f}% ~ {ctr_max:.1f}%**")
            lines.append(
                f"  - 근거: 위 표 3건의 실제 CTR 중 최솟값과 최댓값이나, 이 중 조건까지 실제로 유사한 콘텐츠는 "
                f"{confidence['qualified_count']}건에 불과해 참고용으로만 활용해야 합니다."
            )
        else:
            lines.append(f"- **예상 CTR 범위: {ctr_min:.1f}% ~ {ctr_max:.1f}%**")
            lines.append(
                f"  - 근거: 위 표에서 조건이 가장 유사했던 콘텐츠 {len(top3)}건의 실제 CTR 중 최솟값과 최댓값입니다."
            )
        lines.append("")
        lines.append("**개선 제안 (데이터 근거)**")
        lines.append("")
        if suggestions:
            for i, s in enumerate(suggestions, start=1):
                lines.append(f"{i}. {s}")
        else:
            lines.append("1. 현재 조건이 이미 해당 채널 내 최적 조합에 가까워 추가 제안 없음")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## 종합 코멘트")
    lines.append("")
    lines.append(
        "- 저녁(18~20시)에 발행하고 제목에 이모지를 포함하면, 채널과 관계없이 CTR이 대체로 높게 나타났습니다.\n"
        "- 블로그는 제목이 30자를 초과하는 시점부터 CTR이 크게 하락하므로, 검색 키워드 위주로 제목을 간결하게 "
        "작성하는 것이 바람직합니다.\n"
        "- 더 자세한 수치와 판단 기준은 `decisions.md`에 정리해두었습니다(참고용 — 설계 근거를 더 자세히 알고 "
        "싶은 경우 확인).\n"
        "- 이 진단 결과를 바탕으로 한 발행 전략 기획안은 `strategy_plan.md`에 별도로 정리되어 있습니다."
    )
    lines.append("")
    return "\n".join(lines)


# ---------- 메인 ----------

def run(new_path, past_path, output_path):
    rows = load_past(past_path)
    clean, meta = clean_past(rows)
    agg = compute_aggregates(clean)
    new_rows = load_new(new_path)

    print_step1_summary(rows, clean, meta)
    print_step1_patterns(agg)
    print_step2_pool_check(new_rows, clean)

    report = render_report(new_rows, clean, agg, new_path, past_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"=== [3단계] 리포트 생성 완료: {output_path} ===")


if __name__ == "__main__":
    new_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NEW_PATH
    past_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PAST_PATH
    output_path = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUTPUT_PATH
    run(new_path, past_path, output_path)
