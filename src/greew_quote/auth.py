from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"

MASTER_USERNAME = os.getenv("GREEW_MASTER_USER", "master")
MASTER_PASSWORD = os.getenv("GREEW_MASTER_PASSWORD", "Master@123")


@dataclass(frozen=True)
class AuthUser:
    username: str
    name: str
    is_master: bool
    created_at: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_username(value: str) -> str:
    return value.strip().lower()


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex()


def _verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    try:
        calculated = _hash_password(password, salt_hex)
    except ValueError:
        return False
    return secrets.compare_digest(calculated, expected_hash)


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text(json.dumps({"users": []}, indent=2), encoding="utf-8")


def _load_users() -> list[dict]:
    _ensure_store()
    try:
        raw = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        raw = {"users": []}
    users = raw.get("users", [])
    if not isinstance(users, list):
        return []
    return users


def _save_users(users: list[dict]) -> None:
    _ensure_store()
    USERS_FILE.write_text(json.dumps({"users": users}, indent=2), encoding="utf-8")


def list_registered_users() -> list[AuthUser]:
    users = _load_users()
    output: list[AuthUser] = []
    for user in users:
        output.append(
            AuthUser(
                username=user.get("username", ""),
                name=user.get("name", ""),
                is_master=False,
                created_at=user.get("created_at"),
            )
        )
    output.sort(key=lambda item: item.username)
    return output


def register_user(name: str, username: str, password: str) -> tuple[bool, str]:
    normalized_username = _normalize_username(username)
    cleaned_name = name.strip()

    if not cleaned_name:
        return False, "Informe o nome completo."
    if not normalized_username:
        return False, "Informe um usuario."
    if len(normalized_username) < 3:
        return False, "Usuario precisa ter ao menos 3 caracteres."
    if normalized_username == _normalize_username(MASTER_USERNAME):
        return False, "Este usuario e reservado para o acesso master."
    if len(password) < 6:
        return False, "Senha precisa ter ao menos 6 caracteres."

    users = _load_users()
    username_exists = any(
        _normalize_username(item.get("username", "")) == normalized_username for item in users
    )
    if username_exists:
        return False, "Usuario ja cadastrado."

    salt_hex = secrets.token_hex(16)
    password_hash = _hash_password(password, salt_hex)
    users.append(
        {
            "username": normalized_username,
            "name": cleaned_name,
            "salt": salt_hex,
            "password_hash": password_hash,
            "created_at": _utc_now_iso(),
        }
    )
    _save_users(users)
    return True, "Cadastro realizado com sucesso."


def authenticate(username: str, password: str) -> AuthUser | None:
    normalized_username = _normalize_username(username)

    if normalized_username == _normalize_username(MASTER_USERNAME):
        if secrets.compare_digest(password, MASTER_PASSWORD):
            return AuthUser(
                username=MASTER_USERNAME,
                name="Master",
                is_master=True,
                created_at=None,
            )
        return None

    users = _load_users()
    for user in users:
        if _normalize_username(user.get("username", "")) != normalized_username:
            continue
        if _verify_password(password, user.get("salt", ""), user.get("password_hash", "")):
            return AuthUser(
                username=user.get("username", ""),
                name=user.get("name", ""),
                is_master=False,
                created_at=user.get("created_at"),
            )
    return None
