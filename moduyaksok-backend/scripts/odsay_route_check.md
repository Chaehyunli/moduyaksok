# ODsay 이동 옵션 수동 검증 결과

마지막 실행: 2026-08-10T12:11:51

`scripts/verify_odsay_routes.py` 실행 결과 — `app/services/odsay_directions.py`의 `get_walk_option()`/`get_transit_options()`이 실제로 어떤 값을 돌려주는지, ODsay 원본 응답과 대조해서 확인한다.

## 강남역 -> 서울시청 (충분히 먼 거리, 대중교통 기대)

- 입력 좌표: 강남역(37.497942, 127.027621) -> 서울시청(37.5648, 126.9765)
- 대중교통 옵션 24개 조회됨

### 우리 함수가 파싱한 결과 (조회된 대중교통 옵션 전부)

```json
{
  "get_walk_option": {
    "option_id": "walk",
    "mode": "walk",
    "duration_minutes": 46,
    "fare_krw": 0,
    "transfer_count": 0,
    "description": ""
  },
  "get_transit_options": [
    {
      "option_id": "transit-0",
      "mode": "transit",
      "duration_minutes": 39,
      "fare_krw": 1650,
      "transfer_count": 2,
      "description": "지하철 강남 → 시청"
    },
    {
      "option_id": "transit-1",
      "mode": "transit",
      "duration_minutes": 43,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 지하철2호선강남역 → 소공동주민센터"
    },
    {
      "option_id": "transit-2",
      "mode": "transit",
      "duration_minutes": 42,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 지하철2호선강남역 → 광화문역"
    },
    {
      "option_id": "transit-3",
      "mode": "transit",
      "duration_minutes": 39,
      "fare_krw": 2350,
      "transfer_count": 2,
      "description": "지하철 강남 → 시청"
    },
    {
      "option_id": "transit-4",
      "mode": "transit",
      "duration_minutes": 40,
      "fare_krw": 1650,
      "transfer_count": 2,
      "description": "지하철 강남 → 회현"
    },
    {
      "option_id": "transit-5",
      "mode": "transit",
      "duration_minutes": 41,
      "fare_krw": 1650,
      "transfer_count": 1,
      "description": "지하철 신논현 → 시청"
    },
    {
      "option_id": "transit-6",
      "mode": "transit",
      "duration_minutes": 39,
      "fare_krw": 1650,
      "transfer_count": 1,
      "description": "버스+지하철 지하철2호선강남역 → 시청"
    },
    {
      "option_id": "transit-7",
      "mode": "transit",
      "duration_minutes": 43,
      "fare_krw": 2500,
      "transfer_count": 0,
      "description": "버스 지하철2호선강남역 → 소공동주민센터"
    },
    {
      "option_id": "transit-8",
      "mode": "transit",
      "duration_minutes": 44,
      "fare_krw": 1650,
      "transfer_count": 1,
      "description": "버스+지하철 지하철2호선강남역 → 시청"
    },
    {
      "option_id": "transit-9",
      "mode": "transit",
      "duration_minutes": 45,
      "fare_krw": 1750,
      "transfer_count": 1,
      "description": "버스+지하철 강남역9번출구 → 시청"
    },
    {
      "option_id": "transit-10",
      "mode": "transit",
      "duration_minutes": 40,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 지하철2호선강남역 → 광화문역"
    },
    {
      "option_id": "transit-11",
      "mode": "transit",
      "duration_minutes": 46,
      "fare_krw": 1650,
      "transfer_count": 1,
      "description": "버스+지하철 지하철2호선강남역 → 시청"
    },
    {
      "option_id": "transit-12",
      "mode": "transit",
      "duration_minutes": 48,
      "fare_krw": 1750,
      "transfer_count": 1,
      "description": "버스+지하철 강남역12번출구 → 시청"
    },
    {
      "option_id": "transit-13",
      "mode": "transit",
      "duration_minutes": 44,
      "fare_krw": 2500,
      "transfer_count": 0,
      "description": "버스 강남역12번출구 → 명동.롯데영플라자"
    },
    {
      "option_id": "transit-14",
      "mode": "transit",
      "duration_minutes": 46,
      "fare_krw": 2250,
      "transfer_count": 1,
      "description": "버스+지하철 강남 → 시청앞.덕수궁"
    },
    {
      "option_id": "transit-15",
      "mode": "transit",
      "duration_minutes": 50,
      "fare_krw": 1650,
      "transfer_count": 1,
      "description": "버스+지하철 신논현 → 시청앞.덕수궁"
    },
    {
      "option_id": "transit-16",
      "mode": "transit",
      "duration_minutes": 72,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 지하철2호선강남역 → 시청역8번출구"
    },
    {
      "option_id": "transit-17",
      "mode": "transit",
      "duration_minutes": 50,
      "fare_krw": 2250,
      "transfer_count": 2,
      "description": "버스+지하철 강남 → 시청앞.덕수궁"
    },
    {
      "option_id": "transit-18",
      "mode": "transit",
      "duration_minutes": 48,
      "fare_krw": 1550,
      "transfer_count": 1,
      "description": "버스+지하철 신논현 → 명동.롯데영플라자"
    },
    {
      "option_id": "transit-19",
      "mode": "transit",
      "duration_minutes": 48,
      "fare_krw": 2250,
      "transfer_count": 2,
      "description": "버스+지하철 강남 → 소공동주민센터"
    },
    {
      "option_id": "transit-20",
      "mode": "transit",
      "duration_minutes": 61,
      "fare_krw": 1600,
      "transfer_count": 2,
      "description": "버스 강남역1번출구.역삼세무서 → 시청역8번출구"
    },
    {
      "option_id": "transit-21",
      "mode": "transit",
      "duration_minutes": 65,
      "fare_krw": 1600,
      "transfer_count": 2,
      "description": "버스 강남역1번출구.역삼세무서 → 시청역8번출구"
    },
    {
      "option_id": "transit-22",
      "mode": "transit",
      "duration_minutes": 65,
      "fare_krw": 1600,
      "transfer_count": 2,
      "description": "버스 강남역1번출구.역삼세무서 → 시청역8번출구"
    },
    {
      "option_id": "transit-23",
      "mode": "transit",
      "duration_minutes": 66,
      "fare_krw": 1600,
      "transfer_count": 2,
      "description": "버스 강남역1번출구.역삼세무서 → 시청역8번출구"
    }
  ]
}
```

### ODsay 원본 응답(get_transit_options이 호출하는 것과 동일 요청)

```json
{
  "request_params": {
    "apiKey": "***",
    "SX": 127.027621,
    "SY": 37.497942,
    "EX": 126.9765,
    "EY": 37.5648,
    "OPT": 0,
    "output": "json"
  },
  "status_code": 200,
  "body": {
    "result": {
      "searchType": 0,
      "outTrafficCheck": 0,
      "busCount": 10,
      "subwayCount": 4,
      "subwayBusCount": 10,
      "pointDistance": 8688,
      "startRadius": 700,
      "endRadius": 700,
      "path": [
        {
          "pathType": 1,
          "info": {
            "trafficDistance": 13900.0,
            "totalWalk": 178,
            "totalTime": 39,
            "payment": 1650,
            "busTransitCount": 0,
            "subwayTransitCount": 3,
            "mapObj": "2:2:222:223@3:2:340:330@2:2:203:201",
            "firstStartStation": "강남",
            "lastEndStation": "시청",
            "totalStationCount": 13,
            "busStationCount": 0,
            "subwayStationCount": 13,
            "totalDistance": 14078.0,
            "totalWalkTime": -1,
            "checkIntervalTime": 100,
            "checkIntervalTimeOverYn": "N",
            "totalIntervalTime": 16
          },
          "subPath": [
            {
              "trafficType": 3,
              "distance": 1,
              "sectionTime": 1
            },
            {
              "trafficType": 1,
              "distance": 1200,
              "sectionTime": 2,
              "stationCount": 1,
              "lane": [
                {
                  "name": "수도권 2호선",
                  "subwayCode": 2,
                  "subwayCityCode": 1000
                }
              ],
              "intervalTime": 5,
              "startName": "강남",
              "startX": 127.027618,
              "startY": 37.497949,
              "endName": "교대",
              "endX": 127.014394,
              "endY": 37.493902,
              "way": "교대",
              "wayCode": 2,
              "door": "1-1",
              "startID": 222,
              "endID": 223,
              "startExitNo": "8",
              "startExitX": 127.02718636224867,
              "startExitY": 37.497534149126984,
              "passStopList": {
                "stations": [
                  {
                    "index": 0,
                    "stationID": 222,
                    "stationName": "강남",
                    "x": "127.027619",
                    "y": "37.497952"
                  },
                  {
                    "index": 1,
                    "stationID": 223,
                    "stationName": "교대",
                    "x": "127.014395",
                    "y": "37.493902"
                  }
                ]
              }
            },
            {
              "trafficType": 3,
              "distance": 0,
              "sectionTime": 2
            },
            {
              "trafficType": 1,
              "distance": 11200,
              "sectionTime": 19,
              "stationCount": 10,
              "lane": [
                {
   
```

## 강남역 -> 강남역 근처(700m 이내, 도보만 기대)

- 입력 좌표: 강남역(37.497942, 127.027621) -> 근처 지점(37.4985, 127.028)
- 대중교통 옵션 0개 조회됨

### 우리 함수가 파싱한 결과 (조회된 대중교통 옵션 전부)

```json
{
  "get_walk_option": {
    "option_id": "walk",
    "mode": "walk",
    "duration_minutes": 5,
    "fare_krw": 0,
    "transfer_count": 0,
    "description": ""
  },
  "get_transit_options": "없음"
}
```

### ODsay 원본 응답(get_transit_options이 호출하는 것과 동일 요청)

```json
{
  "request_params": {
    "apiKey": "***",
    "SX": 127.027621,
    "SY": 37.497942,
    "EX": 127.028,
    "EY": 37.4985,
    "OPT": 0,
    "output": "json"
  },
  "status_code": 200,
  "body": {
    "error": {
      "msg": "출, 도착지가 700m이내입니다.",
      "code": "-98"
    }
  }
}
```

## 홍대입구역 -> 합정역 (중간 거리)

- 입력 좌표: 홍대입구역(37.557527, 126.925784) -> 합정역(37.549907, 126.914625)
- 대중교통 옵션 11개 조회됨

### 우리 함수가 파싱한 결과 (조회된 대중교통 옵션 전부)

```json
{
  "get_walk_option": {
    "option_id": "walk",
    "mode": "walk",
    "duration_minutes": 7,
    "fare_krw": 0,
    "transfer_count": 0,
    "description": ""
  },
  "get_transit_options": [
    {
      "option_id": "transit-0",
      "mode": "transit",
      "duration_minutes": 5,
      "fare_krw": 1550,
      "transfer_count": 0,
      "description": "지하철 홍대입구 → 합정"
    },
    {
      "option_id": "transit-1",
      "mode": "transit",
      "duration_minutes": 11,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역"
    },
    {
      "option_id": "transit-2",
      "mode": "transit",
      "duration_minutes": 12,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역2번출구"
    },
    {
      "option_id": "transit-3",
      "mode": "transit",
      "duration_minutes": 17,
      "fare_krw": 1200,
      "transfer_count": 0,
      "description": "버스 서교푸르지오아파트 → 합정역1번출구"
    },
    {
      "option_id": "transit-4",
      "mode": "transit",
      "duration_minutes": 19,
      "fare_krw": 1500,
      "transfer_count": 0,
      "description": "버스 삼진제약 → 합정역6번출구"
    },
    {
      "option_id": "transit-5",
      "mode": "transit",
      "duration_minutes": 19,
      "fare_krw": 1200,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 서교동주민센터.마포신문사"
    },
    {
      "option_id": "transit-6",
      "mode": "transit",
      "duration_minutes": 10,
      "fare_krw": 3000,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역1번출구"
    },
    {
      "option_id": "transit-7",
      "mode": "transit",
      "duration_minutes": 10,
      "fare_krw": 3200,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역1번출구"
    },
    {
      "option_id": "transit-8",
      "mode": "transit",
      "duration_minutes": 10,
      "fare_krw": 3200,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역1번출구"
    },
    {
      "option_id": "transit-9",
      "mode": "transit",
      "duration_minutes": 10,
      "fare_krw": 3200,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역"
    },
    {
      "option_id": "transit-10",
      "mode": "transit",
      "duration_minutes": 10,
      "fare_krw": 3000,
      "transfer_count": 0,
      "description": "버스 홍대입구역 → 합정역"
    }
  ]
}
```

### ODsay 원본 응답(get_transit_options이 호출하는 것과 동일 요청)

```json
{
  "request_params": {
    "apiKey": "***",
    "SX": 126.925784,
    "SY": 37.557527,
    "EX": 126.914625,
    "EY": 37.549907,
    "OPT": 0,
    "output": "json"
  },
  "status_code": 200,
  "body": {
    "result": {
      "searchType": 0,
      "outTrafficCheck": 0,
      "busCount": 10,
      "subwayCount": 1,
      "subwayBusCount": 0,
      "pointDistance": 1299,
      "startRadius": 700,
      "endRadius": 700,
      "path": [
        {
          "pathType": 1,
          "info": {
            "trafficDistance": 1100.0,
            "totalWalk": 176,
            "totalTime": 5,
            "payment": 1550,
            "busTransitCount": 0,
            "subwayTransitCount": 1,
            "mapObj": "2:2:239:238",
            "firstStartStation": "홍대입구",
            "lastEndStation": "합정",
            "totalStationCount": 1,
            "busStationCount": 0,
            "subwayStationCount": 1,
            "totalDistance": 1276.0,
            "totalWalkTime": -1,
            "checkIntervalTime": 100,
            "checkIntervalTimeOverYn": "N",
            "totalIntervalTime": 5
          },
          "subPath": [
            {
              "trafficType": 3,
              "distance": 166,
              "sectionTime": 2
            },
            {
              "trafficType": 1,
              "distance": 1100,
              "sectionTime": 2,
              "stationCount": 1,
              "lane": [
                {
                  "name": "수도권 2호선",
                  "subwayCode": 2,
                  "subwayCityCode": 1000
                }
              ],
              "intervalTime": 5,
              "startName": "홍대입구",
              "startX": 126.924016,
              "startY": 37.557017,
              "endName": "합정",
              "endX": 126.91452,
              "endY": 37.549938,
              "way": "합정",
              "wayCode": 1,
              "door": "null",
              "startID": 239,
              "endID": 238,
              "startExitNo": "4",
              "startExitX": 126.92598985642611,
              "startExitY": 37.55802942928684,
              "endExitNo": "5",
              "endExitX": 126.91426052041118,
              "endExitY": 37.54953256417806,
              "passStopList": {
                "stations": [
                  {
                    "index": 0,
                    "stationID": 239,
                    "stationName": "홍대입구",
                    "x": "126.924019",
                    "y": "37.557016"
                  },
                  {
                    "index": 1,
                    "stationID": 238,
                    "stationName": "합정",
                    "x": "126.914523",
                    "y": "37.549935"
                  }
                ]
              }
            },
            {
              "trafficType": 3,
              "distance": 10,
              "sectionTime": 1
            }
          ]
        },
        {
          "pathType": 2,
          "info": {
          
```
