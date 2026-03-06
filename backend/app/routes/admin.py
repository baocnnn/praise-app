from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/admin")


@router.get("/users", response_model=list[schemas.UserResponse])
def get_all_users(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.User).all()


@router.post("/core-values", response_model=schemas.CoreValueResponse)
def admin_create_core_value(
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


@router.delete("/core-values/{core_value_id}")
def admin_delete_core_value(
    core_value_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    core_value = db.query(models.CoreValue).filter(models.CoreValue.id == core_value_id).first()
    if not core_value:
        raise HTTPException(status_code=404, detail="Core value not found")
    db.delete(core_value)
    db.commit()
    return {"message": "Core value deleted"}


@router.post("/rewards", response_model=schemas.RewardResponse)
def admin_create_reward(
    reward: schemas.RewardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    new_reward = models.Reward(
        name=reward.name,
        description=reward.description,
        point_cost=reward.point_cost
    )
    db.add(new_reward)
    db.commit()
    db.refresh(new_reward)
    return new_reward


@router.delete("/rewards/{reward_id}")
def admin_delete_reward(
    reward_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    reward = db.query(models.Reward).filter(models.Reward.id == reward_id).first()
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found")
    db.delete(reward)
    db.commit()
    return {"message": "Reward deleted"}


@router.patch("/redemptions/{redemption_id}/fulfill")
def admin_fulfill_redemption(
    redemption_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    redemption = db.query(models.Redemption).filter(models.Redemption.id == redemption_id).first()
    if not redemption:
        raise HTTPException(status_code=404, detail="Redemption not found")
    redemption.status = "fulfilled"
    db.commit()
    return {"message": "Redemption fulfilled"}


@router.get("/redemptions")
def admin_get_all_redemptions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Redemption).options(
        joinedload(models.Redemption.reward),
        joinedload(models.Redemption.user)
    ).order_by(models.Redemption.redeemed_at.desc()).all()