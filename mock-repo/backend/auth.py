"""
Mock Auth Module
Handles JWT-based user authentication.
"""
import jwt
import hashlib
from datetime import datetime, timedelta

SECRET_KEY = "mock-secret-key"
ALGORITHM = "HS256"


class AuthService:
    def __init__(self, user_repo):
        self.user_repo = user_repo

    def login(self, username: str, password: str) -> dict:
        user = self.user_repo.find_by_username(username)
        if not user:
            raise ValueError("User not found")
        if not self._verify_password(password, user["password_hash"]):
            raise ValueError("Invalid credentials")
        token = self._generate_jwt(user["id"], user["role"])
        return {"access_token": token, "token_type": "bearer"}

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return hashlib.sha256(password.encode()).hexdigest() == password_hash

    def _generate_jwt(self, user_id: int, role: str) -> str:
        payload = {
            "sub": user_id,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=24),
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return {"valid": True, "user_id": payload["sub"], "role": payload["role"]}
        except jwt.ExpiredSignatureError:
            return {"valid": False, "error": "Token expired"}
        except jwt.InvalidTokenError:
            return {"valid": False, "error": "Invalid token"}
