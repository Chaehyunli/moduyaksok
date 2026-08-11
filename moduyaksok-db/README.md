# 모두약속 — DB

개발용 Postgres + Redis를 docker compose로 띄운다. Postgres 스키마는 `../moduyaksok-backend`의 SQLModel 정의가 원본이며, 마이그레이션은 Alembic(`../moduyaksok-backend/alembic`)으로 관리한다. Redis는 네이버 지역검색 API 일일 호출 카운터 저장용(`../moduyaksok-backend/app/services/rate_limiter.py`, 2026-08-11 추가) — 여러 워커/인스턴스에서도 전역 집계가 맞아야 해서 in-memory 대신 씀.

## 실행

```bash
docker compose up -d      # 시작
docker compose ps         # 상태 확인
docker compose down       # 정지 (볼륨은 유지)
```

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `5433` (로컬 Homebrew Postgres 기본 포트 5432와 충돌 피하려고 5433 사용) |
| User / Password | `moduyaksok` / `moduyaksok` |
| DB | `moduyaksok` |

`backend/.env`의 `DATABASE_URL`이 이 값과 일치해야 한다 (`.env.example` 참고).

### Redis

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `6380` (로컬 Homebrew Redis 기본 포트 6379와 충돌 피하려고 6380 사용, postgres와 같은 이유) |

`backend/.env`의 `REDIS_URL`(`redis://localhost:6380/0`)이 이 값과 일치해야 한다.

## 스키마 적용

컨테이너를 처음 띄운 뒤에는 테이블이 비어 있다. 백엔드에서 Alembic 마이그레이션을 실행해야 테이블이 생긴다.

```bash
cd ../moduyaksok-backend && source .venv/bin/activate
alembic upgrade head
```

## 데이터 초기화

```bash
docker compose down -v    # 볼륨까지 삭제 (모든 데이터 유실)
docker compose up -d
cd ../moduyaksok-backend && alembic upgrade head
```

## 접속 확인

```bash
docker exec -it moduyaksok-db psql -U moduyaksok -d moduyaksok
```
