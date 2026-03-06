from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter()


@router.post("/core-values")
def create_core_value(
    name: str,
    description: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    core_value = models.CoreValue(name=name, description=description)
    db.add(core_value)
    db.commit()
    db.refresh(core_value)
    return core_value


@router.get("/core-values")
def get_core_values(db: Session = Depends(get_db)):
    return db.query(models.CoreValue).all()


@router.post("/praise", response_model=schemas.PraiseResponse)
def give_praise(
    praise: schemas.PraiseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if praise.receiver_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot praise yourself")
    receiver = db.query(models.User).filter(models.User.id == praise.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    core_value = db.query(models.CoreValue).filter(models.CoreValue.id == praise.core_value_id).first()
    if not core_value:
        raise HTTPException(status_code=404, detail="Core value not found")

    points_awarded = 10
    new_praise = models.Praise(
        giver_id=current_user.id,
        receiver_id=praise.receiver_id,
        message=praise.message,
        core_value_id=praise.core_value_id,
        points_awarded=points_awarded
    )
    receiver.points_balance += points_awarded
    current_user.points_balance += 5
    db.add(new_praise)
    db.commit()
    db.refresh(new_praise)
    return new_praise


@router.get("/praise", response_model=list[schemas.PraiseResponse])
def get_all_praise(db: Session = Depends(get_db)):
    return db.query(models.Praise).order_by(models.Praise.created_at.desc()).all()


@router.get("/praise/received", response_model=list[schemas.PraiseResponse])
def get_my_praise(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Praise).filter(
        models.Praise.receiver_id == current_user.id
    ).order_by(models.Praise.created_at.desc()).all()