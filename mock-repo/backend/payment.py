"""
Mock Payment Service
Handles payment processing via Stripe.
"""
import stripe
from backend.auth import AuthService
from backend.database import PaymentRepository

stripe.api_key = "mock-stripe-key"


class PaymentService:
    def __init__(self, auth_service: AuthService, payment_repo: PaymentRepository):
        self.auth = auth_service
        self.repo = payment_repo

    def process_payment(self, token: str, amount: int, currency: str = "usd") -> dict:
        auth_result = self.auth.verify_token(token)
        if not auth_result["valid"]:
            raise PermissionError("Unauthorized: " + auth_result.get("error", ""))

        charge = stripe.Charge.create(
            amount=amount,
            currency=currency,
            source="tok_visa",
            description=f"Payment by user {auth_result['user_id']}",
        )

        self.repo.save_transaction({
            "user_id": auth_result["user_id"],
            "amount": amount,
            "stripe_id": charge.id,
            "status": charge.status,
        })

        return {"success": True, "charge_id": charge.id, "status": charge.status}
