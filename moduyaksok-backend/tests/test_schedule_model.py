# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : schedule_session.status DB CHECK 제약 테스트
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.schedule import ScheduleSession
from app.models.user import User


def _make_user(session: object) -> User:
    user = User(google_id="schedule-test-google-id", email="schedule-test@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.mark.parametrize("status", ["draft", "confirmed"])
def test_allowed_status_values_are_accepted(session, status):
    user = _make_user(session)
    session.add(ScheduleSession(user_id=user.id, status=status))
    session.commit()  # 예외 없이 통과하면 성공


def test_invalid_status_value_is_rejected_by_db(session):
    user = _make_user(session)
    session.add(ScheduleSession(user_id=user.id, status="bogus"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()  # 실패한 커밋 이후 세션을 다시 쓸 수 있는 상태로 되돌림
