# BYOK API 키 — 클라이언트 패스프레이즈 암호화로 전환 설계

**작성일**: 2026-08-17
**상태**: 설계 승인 대기 (브레인스토밍 완료, 사용자 리뷰 전)

## 1. 배경/목표

`docs/기술설계_2026-08-06.md` §3.4에서 "서버(`CREDENTIAL_ENCRYPTION_KEY`
보유자)가 DB의 어떤 사용자 키든 복호화 가능하다"는 신뢰 문제를 검토했고,
당시(2026-08-07, 실사용자 없음 단계)는 "구조를 바꾸지 않는다"로 결정했었다.

이번 설계는 그 결정을 뒤집는다 — **서버가 평문 API 키를 영구 보관/복호화하지
못하게** 구조를 바꾼다. 이제 실사용자가 있는 상태이므로(`user` 테이블은 그대로
유지), 이 변경은 앞으로 등록되는 키부터 적용되고 기존에 저장된 암호문은
마이그레이션 대상이 아니라 **폐기**된다(§6).

핵심 방식: 사용자가 API 키 등록 시 별도 패스프레이즈를 설정 → 브라우저에서
Web Crypto API(PBKDF2 → AES-GCM)로 로컬 암호화 → 서버는 암호문만 저장. 실제
스케줄 생성 시점(파이프라인이 provider를 호출하는 순간)엔 클라이언트가 그때
로컬에서 복호화해 평문을 그 요청에만 실어 보내고, 서버는 처리 후 버린다 —
저장은 물론 사용 시점에도 서버가 스스로 복호화할 방법이 없다.

## 2. 범위

**포함**:
- 프런트: PBKDF2/AES-GCM 유틸(`credentialCrypto.ts`), 패스프레이즈 입력 UI,
  세션 동안 유도키를 메모리에 캐시하는 store, API 키 등록/재확인/스케줄 생성
  화면들이 평문을 요청에 실어 보내도록 수정.
- 백엔드: `llm_credential` 테이블 스키마 변경(salt/iv/kdf_iterations/masked_key
  추가), `POST /me/llm-credential` 계약 변경(암호문 받기), 신규
  `POST /me/llm-credential/verify`(저장 전 임시 테스트), `test` 엔드포인트가
  평문을 body로 받도록 변경, 스케줄 생성 라우터들이 body의 평문 `api_key`를
  쓰도록 변경, 서버 측 Fernet 레이어(`encrypt_key`/`decrypt_key`,
  `CREDENTIAL_ENCRYPTION_KEY`) 제거.
- DB 마이그레이션: 기존 `llm_credential` 행 전체 삭제(새 스킴으로 옮길 방법이
  없음) + 신규 컬럼 추가.
- 문서: `기술설계_2026-08-06.md` §3.4 갱신, `moduyaksok-backend/CLAUDE.md`의
  "BYOK 키 보안" 절 갱신, `API명세서`/`ERD`, 두 `schedule.md`.

**포함 안 함**:
- Argon2 등 WASM 기반 KDF (PBKDF2로 결정, §4.1).
- 기존 암호화 키에 대한 자동 마이그레이션/이중 스킴 지원 — 실사용자 데이터라도
  서버가 패스프레이즈를 대신 만들어줄 수 없으므로 애초에 불가능(§6).
- 영향받는 사용자에게 보낼 안내 이메일/알림 발송 자동화 — 운영 이슈이지 이번
  코드 변경 범위가 아님. 필요하면 별도로 진행.
- 여러 기기 간 패스프레이즈 동기화. 기기마다 다시 입력.

## 3. 전체 아키텍처

```
[등록] (verify 통과가 저장의 필수 전제조건 — 실패하면 저장 자체를 안 함)
브라우저: 패스프레이즈 + API 키(평문) 입력
   → POST /me/llm-credential/verify { provider, api_key(평문) }
   서버: ping_provider 호출 결과만 반환, 저장 안 함
   → 실패 시 "키가 유효하지 않습니다" 피드백하고 여기서 중단
   → 성공 시에만: PBKDF2 유도(salt) → AES-GCM 암호화(iv)
   → POST /me/llm-credential { provider, ciphertext, salt, iv,
                                kdf_iterations, masked_key }
서버: 그대로 저장. 평문을 본 적 없음.

[스케줄 생성 / 키 재확인]
브라우저: GET /me/llm-credential로 ciphertext/salt/iv/kdf_iterations 확보(화면
   진입 시 미리 캐시해두면 이 왕복은 생성 시점에 안 걸림)
   → 캐시된 유도키 있으면 즉시 로컬 복호화, 없으면 패스프레이즈 입력 모달
   → POST .../generate (또는 /test) { ..., api_key(평문) }
서버: 그 요청 처리 중에만 평문 사용, 응답 후 버림. DB엔 안 씀.
```

서버는 `CREDENTIAL_ENCRYPTION_KEY`라는 마스터키 자체를 더는 갖지 않는다 —
자기 힘으로 풀 수 있는 게 없다.

## 4. 컴포넌트별 변경

### 4.1 암호화 파라미터
- KDF: PBKDF2-SHA256, 600,000 iterations (브라우저 `crypto.subtle` 네이티브,
  새 의존성 없음 — Argon2는 WASM 라이브러리가 필요해 기각).
- 암호: AES-GCM 256bit. salt 16byte, iv 12byte, 매 암호화 연산마다 새로 생성.
- `kdf_iterations`를 DB에 같이 저장 — 나중에 반복 횟수를 올려도 기존 행은
  그때 저장된 값으로 복호화 가능해야 하므로. salt/iv/iterations는 비밀이
  아니라 평문 컬럼으로 저장해도 안전.
- `deriveKey`로 만드는 `CryptoKey`는 원칙적으로 `extractable: false`. 단,
  `sessionStorage` 캐시본(§4.5)은 저장을 위해 raw bytes로 export해야 하므로
  그 사본만 `extractable: true`로 유도 — devtools 덤프 방어는 이 지점에서
  포기하는 대신 새로고침 생존 UX를 얻는 의도된 트레이드오프(XSS 앞에서는
  둘 다 어차피 뚫리므로 실질 손실은 작음).

### 4.2 DB 스키마 (`llm_credential`, `app/models/llm_credential.py`)
```python
class LLMCredential(SQLModel, table=True):
    __tablename__ = "llm_credential"
    id: UUID
    user_id: UUID  # unique, 기존과 동일
    provider: str
    encrypted_key: bytes   # 의미 변경: 서버 Fernet 암호문 → 클라이언트 AES-GCM 암호문
    salt: bytes             # 신규
    iv: bytes                # 신규
    kdf_iterations: int      # 신규
    masked_key: str          # 신규 — 클라이언트가 등록 시 계산해서 보냄
    verified_at: datetime | None
    created_at: datetime
```
`app/services/credential.py`의 `encrypt_key`/`decrypt_key`(Fernet 기반)는
삭제. `mask_key`는 프런트로 이동(로직은 앞뒤 몇 글자만 남기는 동일 규칙).

### 4.3 API 계약 (`app/routers/credential.py`)
- `POST /me/llm-credential`: body `{provider, ciphertext, salt, iv,
  kdf_iterations, masked_key}`. `ping_provider` 사전검증 제거(평문이 없음) —
  그 역할은 아래 `/verify`로 이동.
- 신규 `POST /me/llm-credential/verify`: body `{provider, api_key}`(평문).
  기존 `_KEY_PATTERNS` 정규식 검증 + `ping_provider` 호출, 결과만 반환하고
  아무것도 저장하지 않음. **등록 흐름의 필수 선행 단계** — 프런트는 이 호출이
  성공해야만 `POST /me/llm-credential`을 호출함(실패한 키가 저장되는 경로
  자체를 차단). 요청/에러 로깅에 `api_key` 평문이 남지 않도록 주의(로깅
  미들웨어가 요청 body나 예외 스택트레이스를 통째로 남기지 않는지 확인).
- `POST /me/llm-credential/test`: body에 평문 `api_key` 추가 필요. 기존처럼
  DB에서 `encrypted_key`를 꺼내 서버가 복호화하는 로직 제거 — body로 받은
  평문을 그대로 `ping_provider`에 전달하고 `verified_at`만 갱신.
- `GET /me/llm-credential`: `masked_key`뿐 아니라 로컬 복호화에 필요한
  `ciphertext(encrypted_key)`, `salt`, `iv`, `kdf_iterations`도 같이 반환.
  본인 소유 자격증명만 조회 가능한 기존 인증 스코프 그대로라 노출 범위는
  안 늘어남 — 브라우저가 이 값들을 못 받으면 애초에 로컬 복호화가 불가능하기
  때문에 필수. 서버는 여전히 복호화 안 함.
- `DELETE /me/llm-credential`: 변경 없음.

### 4.4 스케줄 생성 라우터 (`app/routers/schedule.py`)
현재 `decrypt_key(credential.encrypted_key)`로 서버가 복호화하는 6곳 이상을
모두 "요청 body의 평문 `api_key` 필드를 그대로 쓴다"로 변경. 파이프라인 함수
시그니처(`api_key: str` 평문 파라미터)는 이미 이렇게 설계돼 있어서
(§3.4 메모) `app/pipeline/*.py`는 무수정.

### 4.5 프런트
- 신규 `src/lib/credentialCrypto.ts`: `deriveKey(passphrase, salt)`,
  `encrypt(plaintext, key)`, `decrypt(ciphertext, key, iv)`, `maskKey(raw)`.
  전부 `crypto.subtle` 기반, 새 npm 의존성 없음.
- 신규 패스프레이즈 세션 캐시: Pinia store + `sessionStorage`. 유도 직후
  `CryptoKey`를 raw bytes로 export → base64 → `sessionStorage`에 저장(Pinia
  상태는 그 위에 얹은 캐시일 뿐, 진짜 소스는 `sessionStorage`). 새로고침해도
  탭이 살아있는 한 유지되고, 탭/창을 닫으면 `sessionStorage`가 자동으로
  비워져 재입력이 필요해짐 — 다른 탭·창과는 애초에 공유 안 됨. 패스프레이즈
  원문 자체는 유도 직후 버림(저장 대상 아님).
- `ApiKeyEditView.vue`: 패스프레이즈 입력 필드 추가 → 로컬 유도 →
  `/verify`로 테스트 → 통과 시 로컬 암호화해서 `POST`.
- 스케줄 생성을 트리거하는 화면들: `GET /me/llm-credential`로 ciphertext/salt/
  iv/kdf_iterations를 가져온 뒤(화면 진입 시 미리 fetch해 캐시해두면 생성
  시점엔 이 왕복이 안 걸림), 캐시된 유도키 있으면 로컬 복호화해서 요청에
  평문 실음, 없으면 패스프레이즈 입력 모달 먼저 → 유도 후 복호화.

## 5. 에러 처리
- **패스프레이즈 오입력**: AES-GCM은 인증 태그가 있어 틀린 키로 복호화하면
  예외를 던진다(다른 대칭암호처럼 "그럴듯한 쓰레기 값"이 안 나옴) — 이 예외를
  잡아 "패스프레이즈가 틀렸어요" 즉시 피드백.
- **패스프레이즈 분실**: 서버가 패스프레이즈를 전혀 모르므로 복구 불가(설계상
  당연한 결과, §3.4에서 이미 예견됨). "등록된 키 삭제 후 재등록"만 안내.
- **유도키 소실**: 탭/창을 닫았다 다시 열거나(`sessionStorage` 자동 소실),
  다른 탭에서 접속했거나, 재로그인한 경우 패스프레이즈 재입력 요구. 같은
  탭 안에서의 새로고침은 `sessionStorage`가 살아있으므로 재입력 불필요.

## 6. 기존 데이터 마이그레이션

`user` 테이블은 그대로 유지 — 이번 변경은 `llm_credential` 테이블에만
해당한다. 기존 `encrypted_key`는 서버 Fernet 마스터키로 암호화된 값이라 새
스킴(클라이언트 패스프레이즈 유도 AES-GCM)으로 옮길 방법이 원천적으로 없다
— 서버가 대신 패스프레이즈를 만들어 줄 수 없기 때문. 서버가 마지막으로
한 번 복호화해봤자 재암호화할 패스프레이즈가 없어 의미가 없다.

Alembic 마이그레이션에서:
1. `llm_credential` 기존 행 전체 삭제(`DELETE FROM llm_credential` 또는
   테이블 재생성).
2. `salt`, `iv`, `kdf_iterations`, `masked_key` 컬럼 추가.

영향받는 사용자(이미 키를 등록해둔 사람)는 배포 후 "등록된 API 키가 없습니다"
상태가 되고, 설정 화면에서 새 패스프레이즈로 한 번 재등록해야 한다. 이건
피할 수 없는 1회성 비용으로 감수한다 — 사전 안내(이메일 등)는 이번 범위 밖.

## 7. 테스트
- 프런트: `credentialCrypto.ts`에 암호화→복호화 라운드트립, 잘못된
  패스프레이즈로 복호화 시 예외 던지는지 vitest 케이스.
- 백엔드: `test_credential.py`의 기존 "평문 api_key를 mock ping_provider로
  검증" 케이스들을 `/verify`·`/test`로 옮기고, `POST /me/llm-credential`은
  "받은 ciphertext/salt/iv를 그대로 저장·반환하는지"만 검증(서버는 더 이상
  암호화 로직을 갖지 않음). `schedule.py` 관련 테스트는 body에 평문
  `api_key`를 채워 넣도록 fixture 조정.

## 8. 문서 동기화 (구현 시 같이)
- `docs/기술설계_2026-08-06.md` §3.4: "2026-08-17, 클라이언트 패스프레이즈
  방식으로 전환" 절 추가, 이 문서를 참조.
- `moduyaksok-backend/CLAUDE.md`의 "BYOK 키 보안" 절: "구조 안 바꾸기로 함"
  결정을 뒤집혔다고 갱신, 새 신뢰 경계 요약.
- `docs/API명세서_2026-08-06.md`, `docs/ERD_2026-08-06.md`: 위 §4.2/4.3 반영.
- `moduyaksok-backend/schedule.md`, `moduyaksok-frontend/schedule.md`: 이번
  작업 항목 추가/완료 표시.
