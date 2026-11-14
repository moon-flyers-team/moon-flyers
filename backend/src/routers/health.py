from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"message": "Moon Flyers API"}


@router.get("/health")
def health():
    return {"status": "ok"}
