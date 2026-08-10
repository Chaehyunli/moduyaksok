# 후보 상세/공유 화면 — 동적 지도 + 교통편 선택 UX 설계

**작성일**: 2026-08-10
**상태**: 설계 승인 대기 (브레인스토밍 완료, 사용자 리뷰 전)

## 1. 배경/목표

지금 `CandidateDetailView`는 장소 카드와 구간별 교통편 옵션 목록을 텍스트로만 쭉
나열한다 — 지도가 없고, 교통편 옵션이 항상 펼쳐진 채로 전체 일정과 뒤섞여
보인다. 이번 작업으로:

1. 장소 마커와 구간별 실제 이동 경로를 지도에 보여준다.
2. 교통편을 선택할 때마다 그 구간의 경로가 지도에 즉시 반영된다.
3. 교통편 선택 UI를 토글(접기/펼치기)로 바꿔 장소 카드와 시각적으로 분리한다.
4. 확정 후 공유 화면(`PublicShareView`)에도 같은 지도를 보여준다 — 이 화면은
   현재 백엔드 없이 브라우저 로컬 상태만 보는 데모라, 실제 공유가 되도록
   백엔드(`GET /share/{slug}`)도 이번에 같이 구현한다.

## 2. 범위

**포함**:
- 백엔드: 자차/대중교통 경로의 실제 좌표(polyline) 확보, 공유 링크
  (`ShareLink` 모델 연결 + `GET /share/{slug}`) 구현.
- 프런트: Naver Maps JS SDK 연동, `CandidateDetailView` 리디자인(장소 카드 +
  교통편 토글 + 상단 고정 지도), `PublicShareView`에 정적 지도 추가.
- 장소 카드에 이미지 영역 추가 — **이번 스코프에선 모든 카드에 동일한 placeholder
  이미지 1장**을 보여준다(신규 정적 에셋). 장소별 실제 사진을 API로 가져오는 건
  범위 밖(§8 참고).

**포함 안 함**:
- 실제 장소 사진 API 연동(placeholder로 대체).
- Step2/3 단계에서 사진을 미리 가져오는 것(애초에 안 함).

## 3. 전체 아키텍처

```
CandidateDetailView (후보 상세, 확정 전)
  ├─ 상단 고정(sticky) 지도 — 장소 마커 + 구간별 "현재 선택된" 경로선
  ├─ 장소 카드 (placeholder 이미지 + 기존 정보)
  └─ 장소 사이 "교통편" 토글 블록
        옵션 선택 → selectOption() 호출 + 토글 자동 닫힘 + 그 구간 지도 갱신

PublicShareView (공유, 확정 후) — 백엔드부터 신규 구현
  ├─ 상단 고정 지도 (토글 없음 — 확정된 경로만 정적으로 표시)
  └─ 장소 카드 (읽기 전용, placeholder 이미지)
```

지도에 그리는 경로선은 **그 구간에서 현재 선택된(`selectedOptionId`) 옵션의
mode를 따라간다** — 자차 API(NCP Directions 5)는 그 구간에서 "자차"가 선택된
경우에만 쓰이고, 같은 일정 안에서도 구간마다 다른 수단이 섞이면 지도에는 각
구간이 실제 선택된 수단의 경로로 각각 그려진다.

## 4. 백엔드 변경

### 4.1 경로 좌표(polyline) 확보

`RouteOption`에 `path: list[tuple[float, float]] = []` 필드 추가(lat, lng 순서).

- **자차**: [naver_directions.py](../../../moduyaksok-backend/app/services/naver_directions.py)가 이미 호출하는 NCP Directions 5 응답의
  `route.trafast[0].path`(좌표 배열, 지금은 버려짐)를 파싱해서 채운다.
- **대중교통(ODsay)**: `searchPubTransPathT` 기본 응답에 경로선 좌표가 있는지
  코드 확인만으로는 확신할 수 없다 — 구현 착수 전에 작은 스크립트로 먼저
  실측한다(이 프로젝트가 이미 여러 번 겪은 "API 문서만 보고 가정하지 말 것"
  패턴). 있으면 파싱, 없으면 직선 폴백으로 처리.
- **도보**: API 호출이 없으므로(직선거리 추정만) 항상 빈 배열 — 프런트가 직선
  폴백을 그린다.

### 4.2 공유 링크 구현

`ShareLink` 모델은 이미 있지만([models/schedule.py:48-54](../../../moduyaksok-backend/app/models/schedule.py#L48-L54)) 연결된 라우터가 없어 안 쓰이고 있었다.

- `ScheduleSession`에 `confirmed_candidate_id: str | None` 컬럼 추가(Alembic
  마이그레이션) — 지금 `POST /confirm`은 후보가 존재하는지만 검증하고 어떤
  후보가 확정됐는지 저장하지 않는다. 공유 화면이 3개 후보 중 뭘 보여줄지
  알려면 필요하다.
- `POST /schedules/{id}/confirm`: 확정 시 `confirmed_candidate_id` 저장 +
  `secrets` 모듈로 8자리 base62 slug 생성해 `ShareLink` row 생성.
- `GET /share/{slug}` (신규, 인증 불필요): slug로 `ShareLink` → `ScheduleSession`
  조회, `confirmed_candidate_id`에 해당하는 후보 하나만 반환(다른 후보·조건·
  사용자 정보는 노출 안 함). slug 없음 → 404.

## 5. 프런트엔드 변경

### 5.1 지도 SDK 연동

Naver Maps JS v3(`ncpKeyId` 방식 — client ID만 필요, secret 불필요). `.env`의
`NAVER_MAP_CLIENT_ID` → `VITE_NAVER_MAP_CLIENT_ID`로 이름 변경. 두 화면에서
재사용하므로 스크립트 중복 로드를 막는 composable `useNaverMapScript()` 도입.

### 5.2 신규 컴포넌트

- **`DoodleMap.vue`**: props `markers: {lat, lng, order}[]`,
  `segments: {path: [lat,lng][], mode}[]`. 마커는 순서 숫자 핀, 각 구간은
  polyline(`path`가 비어있으면 두 마커를 잇는 직선 폴백). `CandidateDetailView`·
  `PublicShareView` 둘 다 재사용(후자는 토글 없이 고정된 `segments` 한 세트만
  전달).
- **`DoodleAccordion.vue`**: 기존 doodle 컴포넌트 목록엔 토글류가 없어 신규 추가.
  펼침 상태를 `expanded` prop/v-model로 부모가 제어(옵션 선택 시 부모가 강제로
  닫아야 하므로).

### 5.3 `CandidateDetailView` 리디자인

- 상단에 `DoodleMap` 고정 배치 — 아래로 스크롤해도 항상 보임.
- 장소 카드: placeholder 이미지 + 기존 정보(카테고리/시간/가격/영업시간 안내)
  유지. 📍 아이콘으로 헤더 표시.
- 장소 카드 사이 교통편 목록을 `DoodleAccordion`으로 감싸 기본 접힘. 헤더에
  현재 선택된 옵션 요약 한 줄(예: "🚌 대중교통 8분 · 1,650원") 표시. 옵션
  클릭 시 `selectOption()` + 아코디언 닫힘 + 지도의 그 구간 polyline 갱신.
  🚌 아이콘으로 장소 카드와 시각 구분(색은 디자인 시스템 제약상 못 씀).

### 5.4 `PublicShareView`

- 백엔드 `GET /share/{slug}` 연동 — 지금의 "링크 만든 브라우저에서만 보임"
  데모 한계 해소.
- 상단 `DoodleMap`(토글 없이 고정 경로) + 장소 카드(읽기 전용, placeholder
  이미지) 추가.

### 5.5 Placeholder 이미지 (임시)

모든 장소 카드에 동일한 손그림 스타일 정적 이미지 1장(`src/assets/` 신규 에셋)을
보여준다. 장소별 실제 사진은 범위 밖(§8).

## 6. 에러 처리

- **지도 SDK 로드 실패**: 지도 영역에 "지도를 불러오지 못했어요" 안내, 장소
  카드/교통편 목록은 정상 동작(지도는 보강 기능이지 필수 경로 아님).
- **polyline 없음**(도보, 또는 대중교통 실측 결과 미제공 시): 직선 폴백.
- **공유 링크**: 존재하지 않는 slug → 404 + "이 링크를 찾을 수 없어요"(기존
  문구 재사용). `confirmed_candidate_id`가 없는 세션 접근 시도 → 404(방어적).

## 7. 테스트 계획

- **백엔드**: `naver_directions.py`/`odsay_directions.py`의 polyline 파싱은
  고정 응답 fixture로 mock 유닛 테스트. `share.py` 라우터는 기존
  `test_schedule.py` 패턴(confirm → slug 생성 → GET 조회, 존재하지 않는 slug 등).
- **프런트**: `npm run build`(타입체크)로 확인. 실제 지도 렌더링·아코디언
  인터랙션은 브라우저 확인이 필요하므로 구현 후 별도로 명시(자동 확인 못
  했다고 보고할 것).
- 이번 변경은 LLM 프롬프트를 안 건드리므로 DeepEval 대상 아님.

## 8. 미해결/추후 스코프

- **장소 사진 실제 API 연동**: 사용자가 "네이버 검색 API 중 사진을 주는 것"을
  언급 — 후보는 네이버 이미지검색 API. 이번엔 placeholder로 대체하고, 실제
  연동은 별도 브레인스토밍으로 진행한다. 연동 시 확인할 것: (1) 엔드포인트가
  레거시 `openapi.naver.com`인지 지역검색처럼 NAVER API HUB로 이관됐는지 실측,
  (2) 인증 헤더가 지역검색과 같은지, (3) `title + roadAddress`(층/호수는
  `naver_map_url._strip_floor_and_unit`로 이미 제거하는 로직 재사용) 검색이
  실제로 그 가게 사진을 주는지 — 키워드 매칭이라 다른 사진이 나올 위험은
  §D(아래 참고)의 메뉴 매칭 문제와 같은 계열.
- **일정 생성 정확도 버그(D)**: 같은 취향 태그가 여러 장소에 중복 반영되는
  문제, verifiable=true 하드 반영의 정밀도 한계(메뉴 데이터 없음)는
  [AI파이프라인_Step별_설계_2026-08-09.md](../../AI파이프라인_Step별_설계_2026-08-09.md)의 "미해결 설계 질문" 절에
  별도로 기록, 결정 보류 상태 — 이번 스펙과는 독립적으로 다음에 다시
  브레인스토밍한다.
- **ODsay 대중교통 polyline 유무**: §4.1에서 실측 전이라고 명시한 대로,
  구현 단계에서 스크립트로 먼저 확인하고 결과에 따라 이 스펙의 "실제 경로선"
  범위가 자차만으로 좁혀질 수 있다.
