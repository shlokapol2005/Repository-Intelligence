"""Mock database models."""


class UserRepository:
    def find_by_username(self, username: str) -> dict | None:
        mock_users = {
            "admin": {"id": 1, "role": "admin", "password_hash": "hashed_pw"},
        }
        return mock_users.get(username)


class PaymentRepository:
    def save_transaction(self, data: dict) -> None:
        print(f"[DB] Saving transaction: {data}")
