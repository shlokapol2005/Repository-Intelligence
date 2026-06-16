"""
Mock FastAPI Routes
"""
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from backend.auth import AuthService
from backend.payment import PaymentService
from backend.database import UserRepository, PaymentRepository

app = FastAPI()
user_repo = UserRepository()
payment_repo = PaymentRepository()
auth_service = AuthService(user_repo)
payment_service = PaymentService(auth_service, payment_repo)


class LoginRequest(BaseModel):
    username: str
    password: str


class PaymentRequest(BaseModel):
    token: str
    amount: int
    currency: str = "usd"


@app.post("/api/login")
def login(req: LoginRequest):
    try:
        return auth_service.login(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/payment")
def payment(req: PaymentRequest):
    try:
        return payment_service.process_payment(req.token, req.amount, req.currency)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok"}
