from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter()


@router.post("/rewards", response_model=schemas.RewardResponse)
def create_reward(
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


@router.get("/rewards", response_model=list[schemas.RewardResponse])
def get_rewards(db: Session = Depends(get_db)):
    return db.query(models.Reward).filter(models.Reward.is_active == True).all()


@router.post("/redeem", response_model=schemas.RedemptionResponse)
def redeem_reward(
    redemption: schemas.RedemptionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    reward = db.query(models.Reward).filter(models.Reward.id == redemption.reward_id).first()
    if not reward or not reward.is_active:
        raise HTTPException(status_code=404, detail="Reward not found")
    if current_user.points_balance < reward.point_cost:
        raise HTTPException(status_code=400, detail="Not enough points")

    new_redemption = models.Redemption(
        user_id=current_user.id,
        reward_id=reward.id,
        points_spent=reward.point_cost,
        status="pending"
    )
    current_user.points_balance -= reward.point_cost
    db.add(new_redemption)
    db.commit()
    db.refresh(new_redemption)
    return new_redemption


@router.get("/my-redemptions", response_model=list[schemas.RedemptionResponse])
def get_my_redemptions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Redemption).filter(
        models.Redemption.user_id == current_user.id
    ).order_by(models.Redemption.redeemed_at.desc()).all()