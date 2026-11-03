"""帳號密碼登入：密碼加鹽雜湊存放、登入工作階段、連續失敗鎖定、登入紀錄、帳號管理。"""
import hashlib
import hmac
import os
import re
import secrets

from .db import connect, query

ROLES = ("業務", "主管", "管理員")
ITERATIONS = 200_000
SESSION_HOURS = 8
MAX_FAILED = 5
LOCK_MINUTES = 15

# 第一次啟動時自動建立的帳號（密碼來自 .env，安裝時隨機產生）
BOOTSTRAP = [
    ("admin", "系統管理員", "管理員", "ADMIN_PASSWORD"),
    ("manager", "示範主管", "主管", "MANAGER_PASSWORD"),
    ("sales", "示範業務", "業務", "SALES_PASSWORD"),
]


class AuthError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def hash_password(password, salt=None):
    """PBKDF2-SHA256，每個密碼各自的隨機鹽；資料庫只存結果，看不到原始密碼。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password, stored):
    _, iterations, salt, digest = stored.split("$")
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(check, digest)


def check_strength(password):
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AuthError(400, "密碼至少 8 碼，且要同時有英文字母和數字")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def bootstrap_users():
    """啟動時補上預設帳號（已存在就不動，避免覆蓋使用者改過的密碼）。"""
    for username, display, role, env in BOOTSTRAP:
        password = os.environ.get(env)
        if not password:
            continue
        query(
            """
            INSERT INTO users (username, display_name, role, password_hash) VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING RETURNING id
            """,
            (username, display, role, hash_password(password)),
        )


def log_event(username, success, reason, ip):
    query(
        "INSERT INTO login_events (username, success, reason, ip) VALUES (%s, %s, %s, %s) RETURNING id",
        (username[:50], success, reason, ip),
    )


def login(username, password, ip=""):
    rows = query("SELECT * FROM users WHERE username = %s", (username,))
    user = rows[0] if rows else None
    if user is None:
        # 帳號不存在也回同樣的訊息，避免被試出有哪些帳號
        log_event(username, False, "帳號不存在", ip)
        raise AuthError(401, "帳號或密碼不正確")
    if not user["is_active"]:
        log_event(username, False, "帳號已停用", ip)
        raise AuthError(403, "帳號已停用，請聯絡管理員")
    locked = query("SELECT locked_until > now() AS locked FROM users WHERE id = %s AND locked_until IS NOT NULL",
                   (user["id"],))
    if locked and locked[0]["locked"]:
        log_event(username, False, "帳號鎖定中", ip)
        raise AuthError(423, f"密碼錯誤太多次，帳號已鎖定，請 {LOCK_MINUTES} 分鐘後再試")
    if not verify_password(password, user["password_hash"]):
        failed = query(
            f"""
            UPDATE users SET failed_attempts = failed_attempts + 1,
                locked_until = CASE WHEN failed_attempts + 1 >= {MAX_FAILED}
                                    THEN now() + interval '{LOCK_MINUTES} minutes' ELSE locked_until END
            WHERE id = %s RETURNING failed_attempts
            """,
            (user["id"],),
        )[0]["failed_attempts"]
        log_event(username, False, f"密碼錯誤（第 {failed} 次）", ip)
        if failed >= MAX_FAILED:
            raise AuthError(423, f"密碼錯誤太多次，帳號已鎖定，請 {LOCK_MINUTES} 分鐘後再試")
        raise AuthError(401, "帳號或密碼不正確")

    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = now() WHERE id = %s",
            (user["id"],),
        )
        session = conn.execute(
            f"""
            INSERT INTO sessions (token_hash, user_id, expires_at)
            VALUES (%s, %s, now() + interval '{SESSION_HOURS} hours') RETURNING expires_at
            """,
            (token_hash(token), user["id"]),
        ).fetchone()
    log_event(username, True, "登入成功", ip)
    return {"token": token, "expires_at": session["expires_at"], "user": public_user(user)}


def public_user(user):
    return {"username": user["username"], "display_name": user["display_name"], "role": user["role"]}


def user_from_token(token):
    """工作階段只存雜湊；過期或帳號停用就失效。"""
    rows = query(
        """
        SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s AND s.expires_at > now() AND u.is_active
        """,
        (token_hash(token),),
    )
    return rows[0] if rows else None


def logout(token):
    query("DELETE FROM sessions WHERE token_hash = %s RETURNING user_id", (token_hash(token),))


def list_users():
    return query(
        """
        SELECT id, username, display_name, role, is_active, failed_attempts,
               (locked_until > now()) AS locked, last_login_at, created_at
        FROM users ORDER BY id
        """
    )


def create_user(username, display_name, role, password):
    if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
        raise AuthError(400, "帳號只能用小寫英文、數字、底線，3 到 30 字")
    if role not in ROLES:
        raise AuthError(400, "角色只能是業務、主管或管理員")
    check_strength(password)
    rows = query(
        """
        INSERT INTO users (username, display_name, role, password_hash) VALUES (%s, %s, %s, %s)
        ON CONFLICT (username) DO NOTHING
        RETURNING id, username, display_name, role, is_active
        """,
        (username, display_name, role, hash_password(password)),
    )
    if not rows:
        raise AuthError(409, "帳號已存在")
    return rows[0]


def update_user(user_id, acting_username, is_active=None, role=None, password=None):
    rows = query("SELECT * FROM users WHERE id = %s", (user_id,))
    if not rows:
        raise AuthError(404, "找不到帳號")
    target = rows[0]
    if target["username"] == acting_username and (is_active is False or (role and role != "管理員")):
        raise AuthError(400, "不能停用自己或拿掉自己的管理員權限")
    if role is not None and role not in ROLES:
        raise AuthError(400, "角色只能是業務、主管或管理員")
    with connect() as conn:
        if is_active is not None:
            conn.execute("UPDATE users SET is_active = %s WHERE id = %s", (is_active, user_id))
            if not is_active:
                conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        if role is not None:
            conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
        if password is not None:
            check_strength(password)
            conn.execute(
                "UPDATE users SET password_hash = %s, failed_attempts = 0, locked_until = NULL WHERE id = %s",
                (hash_password(password), user_id),
            )
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    return [u for u in list_users() if u["id"] == user_id][0]


def login_events(limit=50):
    return query("SELECT * FROM login_events ORDER BY id DESC LIMIT %s", (limit,))
