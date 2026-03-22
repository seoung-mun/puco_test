import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.db.models import User
from app.core.security import create_access_token
from uuid import uuid4

router = APIRouter()

@router.post("/mock-login")
async def mock_login(db: Session = Depends(get_db)):
    """Development-only endpoint. Disabled in production via DEBUG env var."""
    if os.getenv("DEBUG", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")

    user = db.query(User).filter(User.google_id == "mock_google_id").first()
    if not user:
        user = User(
            id=uuid4(),
            google_id="mock_google_id",
            nickname="AI Tester"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(subject=str(user.id))
    return {"access_token": access_token, "token_type": "bearer", "user": user}
