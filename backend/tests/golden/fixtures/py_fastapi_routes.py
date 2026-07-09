from fastapi import APIRouter

router = APIRouter()


@router.get("/users")
async def list_users():
    return []


@router.post("/users")
async def create_user():
    return {}
