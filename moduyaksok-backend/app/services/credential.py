# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : LLM API 키 암호화/복호화, 마스킹
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.credential_encryption_key.encode())


def encrypt_key(raw_key: str) -> bytes:
    return _fernet().encrypt(raw_key.encode())


def decrypt_key(encrypted_key: bytes) -> str:
    return _fernet().decrypt(encrypted_key).decode()


def mask_key(raw_key: str) -> str:
    return raw_key[:7] + "••••••••" + raw_key[-4:]
