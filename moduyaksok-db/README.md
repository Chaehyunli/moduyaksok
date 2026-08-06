# 모두약속 — DB

개발용 Postgres를 docker compose로 띄운다. 스키마는 `../moduyaksok-backend`의 SQLModel 정의가 원본이며, 마이그레이션은 Alembic(`../moduyaksok-backend/alembic`)으로 관리한다.

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
