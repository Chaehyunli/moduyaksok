# Provider 비교 리포트 (성능 vs 비용)

마지막 실행: 2026-08-12T12:12:38

judge: `upstage` (`solar-pro`) 고정 — 비교 대상 provider가 몇 개든 채점 기준이 흔들리지 않게 하나로 고정했다 (tests/eval/conftest.resolve_eval_credential()가 고른 것 그대로 재사용).

파이프라인 그대로 재현: Step1(LOW, 1회 호출) → Step2(MID, 관점 3개 병렬 호출, 토큰은 3개 합산) → Step3(HIGH, 1회 호출). `orchestrate.py`가 하는 "관점별 최대 1회 재시도"는 여기 반영 안 됨 — 실제 운영 비용은 이보다 약간 더 나올 수 있다.

## anthropic

| step | case | score | pass | input_tok | output_tok | cost(USD) |
|---|---|---|---|---|---|---|
| 1 | basic_multi_item | 0.80 | PASS | 2266 | 124 | $0.0029 |
| 1 | negation_should_not_leak_into_liked | 0.90 | PASS | 2257 | 87 | $0.0027 |
| 1 | empty_text_means_empty_tags | 1.00 | PASS | 2240 | 56 | $0.0025 |
| 1 | vague_text_should_not_invent_specifics | 1.00 | PASS | 2247 | 56 | $0.0025 |
| 1 | reasoning_plus_items | 0.80 | PASS | 2342 | 205 | $0.0034 |
| 1 | atmosphere_not_food | 0.80 | PASS | 2273 | 169 | $0.0031 |
| 1 | crowdedness_is_subjective | 0.80 | PASS | 2251 | 76 | $0.0026 |
| 1 | specific_brand_name | 1.00 | PASS | 2260 | 92 | $0.0027 |
| 1 | only_disliked_filled | 1.00 | PASS | 2263 | 103 | $0.0028 |
| 2 | hard_exclude_verifiable_true_dislike | 0.80 | PASS | 8698 | 2097 | $0.0575 |
| 2 | soft_signal_crowdedness_needs_hedge | 0.80 | PASS | 8641 | 2056 | $0.0568 |
| 2 | no_hallucinated_places_small_candidate_list | 0.80 | PASS | 7969 | 1948 | $0.0531 |
| 2 | budget_conscious_selection | 0.80 | PASS | 8428 | 1877 | $0.0534 |
| 3 | hard_drop_disliked_verifiable_true_via_category | 0.80 | PASS | 1895 | 472 | $0.0213 |
| 3 | soft_signal_never_used_as_drop_reason_and_needs_hedge | 0.80 | PASS | 1810 | 417 | $0.0195 |
| 3 | similar_candidates_get_differentiated_why_recommended | 0.90 | PASS | 1876 | 420 | $0.0199 |
| 3 | all_candidates_violate_same_hard_constraint_becomes_infeasible | 1.00 | PASS | 1740 | 202 | $0.0137 |

**스텝별 평균**

| step | avg score | avg cost(USD) |
|---|---|---|
| 1 | 0.90 | $0.0028 |
| 2 | 0.80 | $0.0552 |
| 3 | 0.88 | $0.0186 |

**일정 하나 생성 예상 비용(Step1+2+3 평균 합, 재시도 미포함): $0.0766**

## upstage

| step | case | score | pass | input_tok | output_tok | cost(USD) |
|---|---|---|---|---|---|---|
| 1 | basic_multi_item | 1.00 | PASS | 952 | 98 | $0.0002 |
| 1 | negation_should_not_leak_into_liked | 0.80 | PASS | 946 | 59 | $0.0002 |
| 1 | empty_text_means_empty_tags | 1.00 | PASS | 942 | 18 | $0.0002 |
| 1 | vague_text_should_not_invent_specifics | 1.00 | PASS | 945 | 18 | $0.0002 |
| 1 | reasoning_plus_items | 0.80 | PASS | 976 | 138 | $0.0002 |
| 1 | atmosphere_not_food | 0.90 | PASS | 949 | 65 | $0.0002 |
| 1 | crowdedness_is_subjective | 0.90 | PASS | 944 | 40 | $0.0002 |
| 1 | specific_brand_name | 1.00 | PASS | 948 | 59 | $0.0002 |
| 1 | only_disliked_filled | 1.00 | PASS | 949 | 62 | $0.0002 |
| 2 | hard_exclude_verifiable_true_dislike | 0.80 | PASS | 3718 | 1087 | $0.0012 |
| 2 | soft_signal_crowdedness_needs_hedge | 0.60 | FAIL | 3679 | 1123 | $0.0012 |
| 2 | no_hallucinated_places_small_candidate_list | 0.20 | FAIL | 3385 | 955 | $0.0011 |
| 2 | budget_conscious_selection | 0.70 | PASS | 3601 | 972 | $0.0011 |
| 3 | hard_drop_disliked_verifiable_true_via_category | 0.80 | PASS | 798 | 278 | $0.0003 |
| 3 | soft_signal_never_used_as_drop_reason_and_needs_hedge | 0.80 | PASS | 750 | 131 | $0.0002 |
| 3 | similar_candidates_get_differentiated_why_recommended | 1.00 | PASS | 797 | 116 | $0.0002 |
| 3 | all_candidates_violate_same_hard_constraint_becomes_infeasible | 1.00 | PASS | 711 | 104 | $0.0002 |

**스텝별 평균**

| step | avg score | avg cost(USD) |
|---|---|---|
| 1 | 0.93 | $0.0002 |
| 2 | 0.57 | $0.0012 |
| 3 | 0.90 | $0.0002 |

**일정 하나 생성 예상 비용(Step1+2+3 평균 합, 재시도 미포함): $0.0015**
