# 파이프라인 소요시간 실측 결과

마지막 실행: 2026-08-10T14:47:27

`scripts/measure_pipeline_timing.py` 실행 결과 — Step1→2→3 실제 호출(네이버 지역검색·LLM 전부 진짜) 소요시간. "재시도 강제" 케이스는 Step2가 만든 후보 1개의 좌표를 스크립트가 직접 지워서 Step3의 장소 환각 하드 위반을 결정론적으로 재현한 것 — LLM 운에 기대지 않는다.

## 사용자 입력 조건

`POST /schedules` 요청 바디 그대로(가정) — 아래 두 케이스 다 이 조건 하나를 공유한다:

```json
{
  "purpose": "date",
  "headcount": 2,
  "time_range": [
    "2026-08-15T10:00:00",
    "2026-08-15T21:00:00"
  ],
  "regions": [
    "서울 강남"
  ],
  "liked_text": "카페나 맛집 위주로, 조용한 곳이 좋아요",
  "disliked_text": "해산물은 못 먹어요",
  "budget_per_person": 50000
}
```

Step1이 liked_text/disliked_text에서 뽑아낸 구조화 조건(`NormalizedConditions`, 나머지 필드는 입력 그대로 통과):

```json
{
  "purpose": "date",
  "headcount": 2,
  "time_range": [
    "2026-08-15T10:00:00",
    "2026-08-15T21:00:00"
  ],
  "regions": [
    "서울 강남"
  ],
  "liked_tags": [
    {
      "tag": "조용한 곳",
      "verifiable": false
    }
  ],
  "disliked_tags": [
    {
      "tag": "해산물",
      "verifiable": true
    }
  ],
  "budget_per_person": 50000
}
```

## 공통 준비 단계 (양쪽 케이스가 공유)

| 단계 | 소요시간(초) |
|---|---|
| [공통] 네이버 지역검색 (place_candidates 조회) | 1.18 |
| [공통] Step1 — 조건 정규화 | 1.31 |
| **소계** | **2.49** |

## 재시도 없는 케이스

| 단계 | 소요시간(초) |
|---|---|
| [재시도 없음] Step2 — 후보 생성(관점 3개) | 2.92 |
| [재시도 없음] Step3 — 검증·병합 | 1.93 |
| **소계** | **4.85** |
| **공통 준비 단계 포함 총합** | **7.34** |

결과: ScheduleResponse, 후보 3개 (강남 데이트: 실내 중심의 가성비 일정, 강남 데이트코스: 코엑스 인근 산책과 한적한 카페 탐방, 조용한 데이트를 위한 강남 일정)

실제 생성된 후보 전체(Step3까지의 응답 — `routes`는 항상 빈 배열, Step4는 사용자가 후보 하나를 고른 뒤에만 별도로 실행됨):

```json
{
  "session_id": "timing-no-retry",
  "candidates": [
    {
      "candidate_id": "A",
      "title": "강남 데이트: 실내 중심의 가성비 일정",
      "why_recommended": "실내에서 조용하고 한산한 카페 및 미술관을 포함하며, 예산을 준수하면서 해산물이 없는 닭갈비와 디저트 옵션을 제공합니다",
      "activities": [
        {
          "order": 1,
          "name": "노티드 스튜디오 청담",
          "category": "음식점>카페,디저트>카페",
          "address": "서울특별시 강남구 도산대로53길 15 1층",
          "start_time": "10:00",
          "end_time": "11:30",
          "price_range_per_person": [
            5000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%85%B8%ED%8B%B0%EB%93%9C%20%EC%8A%A4%ED%8A%9C%EB%94%94%EC%98%A4%20%EC%B2%AD%EB%8B%B4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EB%8F%84%EC%82%B0%EB%8C%80%EB%A1%9C53%EA%B8%B8%2015%201%EC%B8%B5"
        },
        {
          "order": 2,
          "name": "장인닭갈비 강남점",
          "category": "한식>닭갈비",
          "address": "서울특별시 강남구 테헤란로1길 19",
          "start_time": "11:46",
          "end_time": "13:16",
          "price_range_per_person": [
            10000,
            20000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%9E%A5%EC%9D%B8%EB%8B%AD%EA%B0%88%EB%B9%84%20%EA%B0%95%EB%82%A8%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C1%EA%B8%B8%2019"
        },
        {
          "order": 3,
          "name": "셀렉티드닉스",
          "category": "음식점>카페,디저트",
          "address": "서울특별시 강남구 테헤란로4길 37 1층",
          "start_time": "13:27",
          "end_time": "14:57",
          "price_range_per_person": [
            6000,
            12000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%85%80%EB%A0%89%ED%8B%B0%EB%93%9C%EB%8B%89%EC%8A%A4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C4%EA%B8%B8%2037%201%EC%B8%B5"
        },
        {
          "order": 4,
          "name": "마이아트뮤지엄",
          "category": "문화,예술>미술관",
          "address": "서울특별시 강남구 테헤란로 518 섬유센터빌딩 B1층",
          "start_time": "15:13",
          "end_time": "16:43",
          "price_range_per_person": [
            5000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%A7%88%EC%9D%B4%EC%95%84%ED%8A%B8%EB%AE%A4%EC%A7%80%EC%97%84%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C%20518%20%EC%84%AC%EC%9C%A0%EC%84%BC%ED%84%B0%EB%B9%8C%EB%94%A9%20B1%EC%B8%B5"
        }
      ],
      "routes": [],
      "feasibility_warning": "비교적 한산한 편일 수 있어요"
    },
    {
      "candidate_id": "B",
      "title": "강남 데이트코스: 코엑스 인근 산책과 한적한 카페 탐방",
      "why_recommended": "코엑스 인근에 집중된 동선으로 이동 거리를 최소화하면서도 해산물이 없고 비교적 한적한 미술관과 베이커리 카페를 포함합니다",
      "activities": [
        {
          "order": 1,
          "name": "솥내음 스타필드 코엑스몰점",
          "category": "음식점>한식",
          "address": "서울특별시 강남구 영동대로 513 지하1층 O-107호 라운지",
          "start_time": "10:00",
          "end_time": "11:30",
          "price_range_per_person": [
            15000,
            25000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%86%A5%EB%82%B4%EC%9D%8C%20%EC%8A%A4%ED%83%80%ED%95%84%EB%93%9C%20%EC%BD%94%EC%97%91%EC%8A%A4%EB%AA%B0%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EC%98%81%EB%8F%99%EB%8C%80%EB%A1%9C%20513%20%EC%A7%80%ED%95%981%EC%B8%B5%20O-107%ED%98%B8%20%EB%9D%BC%EC%9A%B4%EC%A7%80"
        },
        {
          "order": 2,
          "name": "코엑스",
          "category": "문화,예술>컨벤션센터",
          "address": "서울특별시 강남구 영동대로 513",
          "start_time": "11:35",
          "end_time": "13:05",
          "price_range_per_person": [
            5000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%BD%94%EC%97%91%EC%8A%A4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EC%98%81%EB%8F%99%EB%8C%80%EB%A1%9C%20513"
        },
        {
          "order": 3,
          "name": "런던베이글뮤지엄 도산",
          "category": "카페,디저트>베이커리",
          "address": "서울특별시 강남구 언주로168길 33 1, 2층",
          "start_time": "13:19",
          "end_time": "14:49",
          "price_range_per_person": [
            7000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%9F%B0%EB%8D%98%EB%B2%A0%EC%9D%B4%EA%B8%80%EB%AE%A4%EC%A7%80%EC%97%84%20%EB%8F%84%EC%82%B0%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EC%96%B8%EC%A3%BC%EB%A1%9C168%EA%B8%B8%2033%201%2C%202%EC%B8%B5"
        },
        {
          "order": 4,
          "name": "마이아트뮤지엄",
          "category": "문화,예술>미술관",
          "address": "서울특별시 강남구 테헤란로 518 섬유센터빌딩 B1층",
          "start_time": "15:05",
          "end_time": "16:35",
          "price_range_per_person": [
            10000,
            20000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%A7%88%EC%9D%B4%EC%95%84%ED%8A%B8%EB%AE%A4%EC%A7%80%EC%97%84%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C%20518%20%EC%84%AC%EC%9C%A0%EC%84%BC%ED%84%B0%EB%B9%8C%EB%94%A9%20B1%EC%B8%B5"
        }
      ],
      "routes": [],
      "feasibility_warning": "1인당 총 예산이 59,000원으로 약간 초과할 수 있어요"
    },
    {
      "candidate_id": "C",
      "title": "조용한 데이트를 위한 강남 일정",
      "why_recommended": "해산물을 완전히 배제하고 찌개/전골 등 한식 다양성을 강조하며, K현대미술관 등 조용한 환경을 제공하는 문화 시설을 포함합니다",
      "activities": [
        {
          "order": 1,
          "name": "장인닭갈비 강남점",
          "category": "한식>닭갈비",
          "address": "서울특별시 강남구 테헤란로1길 19",
          "start_time": "10:00",
          "end_time": "11:30",
          "price_range_per_person": [
            12000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%9E%A5%EC%9D%B8%EB%8B%AD%EA%B0%88%EB%B9%84%20%EA%B0%95%EB%82%A8%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C1%EA%B8%B8%2019"
        },
        {
          "order": 2,
          "name": "부대찌개대사관 선릉직영점",
          "category": "한식>찌개,전골",
          "address": "서울특별시 강남구 선릉로86길 24 지상 1층",
          "start_time": "11:42",
          "end_time": "13:12",
          "price_range_per_person": [
            10000,
            13000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%B6%80%EB%8C%80%EC%B0%8C%EA%B0%9C%EB%8C%80%EC%82%AC%EA%B4%80%20%EC%84%A0%EB%A6%89%EC%A7%81%EC%98%81%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EC%84%A0%EB%A6%89%EB%A1%9C86%EA%B8%B8%2024%20%EC%A7%80%EC%83%81%201%EC%B8%B5"
        },
        {
          "order": 3,
          "name": "노티드 스튜디오 청담",
          "category": "음식점>카페,디저트>카페",
          "address": "서울특별시 강남구 도산대로53길 15 1층",
          "start_time": "13:26",
          "end_time": "14:56",
          "price_range_per_person": [
            5000,
            7000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%85%B8%ED%8B%B0%EB%93%9C%20%EC%8A%A4%ED%8A%9C%EB%94%94%EC%98%A4%20%EC%B2%AD%EB%8B%B4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EB%8F%84%EC%82%B0%EB%8C%80%EB%A1%9C53%EA%B8%B8%2015%201%EC%B8%B5"
        },
        {
          "order": 4,
          "name": "K현대미술관",
          "category": "문화,예술>미술관",
          "address": "서울특별시 강남구 선릉로 807 K현대미술관",
          "start_time": "15:01",
          "end_time": "16:31",
          "price_range_per_person": [
            3000,
            5000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/K%ED%98%84%EB%8C%80%EB%AF%B8%EC%88%A0%EA%B4%80%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EC%84%A0%EB%A6%89%EB%A1%9C%20807%20K%ED%98%84%EB%8C%80%EB%AF%B8%EC%88%A0%EA%B4%80"
        }
      ],
      "routes": [],
      "feasibility_warning": "비교적 한산한 편일 수 있어요"
    }
  ]
}
```

## 재시도 강제 케이스

| 단계 | 소요시간(초) |
|---|---|
| [재시도 강제] Step2 — 후보 생성(관점 3개) | 2.81 |
| [재시도 강제] Step3 — 1차 검증(강제로 1개 드롭됨) | 1.64 |
| [재시도 강제] Step2 — 관점 재생성(실내 중심, 가성비 우선) | 2.50 |
| [재시도 강제] Step3 — 2차 검증(재생성분 포함) | 2.11 |
| **소계** | **9.06** |
| **공통 준비 단계 포함 총합** | **11.55** |

결과: ScheduleResponse, 후보 3개 (강남 데이트코스, 데이트를 위한 강남 한적 코스, 강남 데이트 일정 초안)

실제 생성된 후보 전체(Step3까지의 응답 — `routes`는 항상 빈 배열, Step4는 사용자가 후보 하나를 고른 뒤에만 별도로 실행됨):

```json
{
  "session_id": "timing-retry",
  "candidates": [
    {
      "candidate_id": "A",
      "title": "강남 데이트코스",
      "why_recommended": "테헤란로 인근의 인접 장소들로 동선 효율성이 높아 시간 관리가 용이합니다",
      "activities": [
        {
          "order": 1,
          "name": "장인닭갈비 강남점",
          "category": "한식>닭갈비",
          "address": "서울특별시 강남구 테헤란로1길 19",
          "start_time": "10:00",
          "end_time": "11:30",
          "price_range_per_person": [
            12000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%9E%A5%EC%9D%B8%EB%8B%AD%EA%B0%88%EB%B9%84%20%EA%B0%95%EB%82%A8%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C1%EA%B8%B8%2019"
        },
        {
          "order": 2,
          "name": "셀렉티드닉스",
          "category": "음식점>카페,디저트",
          "address": "서울특별시 강남구 테헤란로4길 37 1층",
          "start_time": "11:41",
          "end_time": "13:11",
          "price_range_per_person": [
            8000,
            12000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%85%80%EB%A0%89%ED%8B%B0%EB%93%9C%EB%8B%89%EC%8A%A4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C4%EA%B8%B8%2037%201%EC%B8%B5"
        },
        {
          "order": 3,
          "name": "마이아트뮤지엄",
          "category": "문화,예술>미술관",
          "address": "서울특별시 강남구 테헤란로 518 섬유센터빌딩 B1층",
          "start_time": "13:27",
          "end_time": "14:57",
          "price_range_per_person": [
            5000,
            8000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%A7%88%EC%9D%B4%EC%95%84%ED%8A%B8%EB%AE%A4%EC%A7%80%EC%97%84%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C%20518%20%EC%84%AC%EC%9C%A0%EC%84%BC%ED%84%B0%EB%B9%8C%EB%94%A9%20B1%EC%B8%B5"
        }
      ],
      "routes": [],
      "feasibility_warning": "강남 지역 내 동선 최소화로 이동 시간이 짧을 수 있습니다"
    },
    {
      "candidate_id": "B",
      "title": "데이트를 위한 강남 한적 코스",
      "why_recommended": "1번 후보는 '노티드 스튜디오 청담'을 포함하는데, 이 카페는 데이트에 적합한 독특한 분위기로 차별점이 있습니다",
      "activities": [
        {
          "order": 1,
          "name": "노티드 스튜디오 청담",
          "category": "음식점>카페,디저트>카페",
          "address": "서울특별시 강남구 도산대로53길 15 1층",
          "start_time": "10:00",
          "end_time": "11:30",
          "price_range_per_person": [
            15000,
            20000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%85%B8%ED%8B%B0%EB%93%9C%20%EC%8A%A4%ED%8A%9C%EB%94%94%EC%98%A4%20%EC%B2%AD%EB%8B%B4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EB%8F%84%EC%82%B0%EB%8C%80%EB%A1%9C53%EA%B8%B8%2015%201%EC%B8%B5"
        },
        {
          "order": 2,
          "name": "장인닭갈비 강남점",
          "category": "한식>닭갈비",
          "address": "서울특별시 강남구 테헤란로1길 19",
          "start_time": "11:46",
          "end_time": "13:16",
          "price_range_per_person": [
            12000,
            18000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%9E%A5%EC%9D%B8%EB%8B%AD%EA%B0%88%EB%B9%84%20%EA%B0%95%EB%82%A8%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C1%EA%B8%B8%2019"
        },
        {
          "order": 3,
          "name": "마이아트뮤지엄",
          "category": "문화,예술>미술관",
          "address": "서울특별시 강남구 테헤란로 518 섬유센터빌딩 B1층",
          "start_time": "13:32",
          "end_time": "15:02",
          "price_range_per_person": [
            10000,
            15000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%A7%88%EC%9D%B4%EC%95%84%ED%8A%B8%EB%AE%A4%EC%A7%80%EC%97%84%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C%20518%20%EC%84%AC%EC%9C%A0%EC%84%BC%ED%84%B0%EB%B9%8C%EB%94%A9%20B1%EC%B8%B5"
        }
      ],
      "routes": [],
      "feasibility_warning": "청담과 강남 간 이동 시 교통 상황을 고려해야 할 수 있습니다"
    },
    {
      "candidate_id": "C",
      "title": "강남 데이트 일정 초안",
      "why_recommended": "2번 후보는 가성비 면에서 우수하며, 특히 미술관 비용이 가장 저렴해 예산 여유가 큽니다",
      "activities": [
        {
          "order": 1,
          "name": "노티드 스튜디오 청담",
          "category": "음식점>카페,디저트>카페",
          "address": "서울특별시 강남구 도산대로53길 15 1층",
          "start_time": "10:00",
          "end_time": "11:30",
          "price_range_per_person": [
            15000,
            20000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EB%85%B8%ED%8B%B0%EB%93%9C%20%EC%8A%A4%ED%8A%9C%EB%94%94%EC%98%A4%20%EC%B2%AD%EB%8B%B4%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EB%8F%84%EC%82%B0%EB%8C%80%EB%A1%9C53%EA%B8%B8%2015%201%EC%B8%B5"
        },
        {
          "order": 2,
          "name": "장인닭갈비 강남점",
          "category": "한식>닭갈비",
          "address": "서울특별시 강남구 테헤란로1길 19",
          "start_time": "11:46",
          "end_time": "13:16",
          "price_range_per_person": [
            15000,
            20000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/%EC%9E%A5%EC%9D%B8%EB%8B%AD%EA%B0%88%EB%B9%84%20%EA%B0%95%EB%82%A8%EC%A0%90%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%85%8C%ED%97%A4%EB%9E%80%EB%A1%9C1%EA%B8%B8%2019"
        },
        {
          "order": 3,
          "name": "K현대미술관",
          "category": "문화,예술>미술관",
          "address": "서울특별시 강남구 선릉로 807 K현대미술관",
          "start_time": "13:32",
          "end_time": "15:02",
          "price_range_per_person": [
            5000,
            10000
          ],
          "operating_hours": "",
          "phone": null,
          "info_needs_check": true,
          "map_url": "https://map.naver.com/p/search/K%ED%98%84%EB%8C%80%EB%AF%B8%EC%88%A0%EA%B4%80%20%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%EC%84%A0%EB%A6%89%EB%A1%9C%20807%20K%ED%98%84%EB%8C%80%EB%AF%B8%EC%88%A0%EA%B4%80"
        }
      ],
      "routes": [],
      "feasibility_warning": "K현대미술관 입장료가 저렴하지만 전시 내용에 따라 선호도가 갈릴 수 있습니다"
    }
  ]
}
```
