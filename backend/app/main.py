from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta
from contextlib import asynccontextmanager
from . import models, schemas, auth
from .database import engine, get_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    yield
app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://*.vercel.app",
        "https://*.netlify.app",
        "*",  
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ============== AUTHENTICATION ENDPOINTS ==============

@app.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        points_balance=0
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login and get access token"""
    # Find user by email (username field is used for email)
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    # Verify user exists and password is correct
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
@app.post("/token", response_model=schemas.Token)
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 compatible token endpoint (same as login)"""
    # Find user by email (username field is used for email)
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    # Verify user exists and password is correct
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
    # Create access token
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    """Get current logged-in user info"""
    return current_user
# ============== CORE VALUES ENDPOINTS ==============

@app.post("/core-values")
def create_core_value(name: str, description: str = "", db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Create a new core value (admin only for now)"""
    core_value = models.CoreValue(name=name, description=description)
    db.add(core_value)
    db.commit()
    db.refresh(core_value)
    return core_value

@app.get("/core-values")
def get_core_values(db: Session = Depends(get_db)):
    """Get all core values"""
    return db.query(models.CoreValue).all()
# ============== PRAISE ENDPOINTS ==============

@app.post("/praise", response_model=schemas.PraiseResponse)
def give_praise(
    praise: schemas.PraiseCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Give praise to another user"""
    # Can't praise yourself
    if praise.receiver_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot praise yourself")
    
    # Check if receiver exists
    receiver = db.query(models.User).filter(models.User.id == praise.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    
    # Check if core value exists
    core_value = db.query(models.CoreValue).filter(models.CoreValue.id == praise.core_value_id).first()
    if not core_value:
        raise HTTPException(status_code=404, detail="Core value not found")
    
    # Create praise
    points_awarded = 10  # Default points
    new_praise = models.Praise(
        giver_id=current_user.id,
        receiver_id=praise.receiver_id,
        message=praise.message,
        core_value_id=praise.core_value_id,
        points_awarded=points_awarded
    )
    
    # Update receiver's points
    receiver.points_balance += points_awarded
    
    # Update giver's points (incentivize giving praise)
    current_user.points_balance += 5  # Giver gets 5 points
    
    db.add(new_praise)
    db.commit()
    db.refresh(new_praise)
    
    return new_praise

@app.get("/praise", response_model=list[schemas.PraiseResponse])
def get_all_praise(db: Session = Depends(get_db)):
    """Get all praise (for the dashboard)"""
    return db.query(models.Praise).order_by(models.Praise.created_at.desc()).all()

@app.get("/praise/received", response_model=list[schemas.PraiseResponse])
def get_my_praise(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all praise received by the current user"""
    return db.query(models.Praise).filter(
        models.Praise.receiver_id == current_user.id
    ).order_by(models.Praise.created_at.desc()).all()
# ============== REWARDS ENDPOINTS ==============

@app.post("/rewards", response_model=schemas.RewardResponse)
def create_reward(
    reward: schemas.RewardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new reward (admin only for now)"""
    new_reward = models.Reward(
        name=reward.name,
        description=reward.description,
        point_cost=reward.point_cost
    )
    db.add(new_reward)
    db.commit()
    db.refresh(new_reward)
    return new_reward

@app.get("/rewards", response_model=list[schemas.RewardResponse])
def get_rewards(db: Session = Depends(get_db)):
    """Get all active rewards"""
    return db.query(models.Reward).filter(models.Reward.is_active == True).all()

@app.post("/redeem", response_model=schemas.RedemptionResponse)
def redeem_reward(
    redemption: schemas.RedemptionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Redeem a reward"""
    # Check if reward exists
    reward = db.query(models.Reward).filter(models.Reward.id == redemption.reward_id).first()
    if not reward or not reward.is_active:
        raise HTTPException(status_code=404, detail="Reward not found")
    
    # Check if user has enough points
    if current_user.points_balance < reward.point_cost:
        raise HTTPException(status_code=400, detail="Not enough points")
    
    # Create redemption
    new_redemption = models.Redemption(
        user_id=current_user.id,
        reward_id=reward.id,
        points_spent=reward.point_cost,
        status="pending"
    )
    
    # Deduct points from user
    current_user.points_balance -= reward.point_cost
    
    db.add(new_redemption)
    db.commit()
    db.refresh(new_redemption)
    
    return new_redemption

@app.get("/my-redemptions", response_model=list[schemas.RedemptionResponse])
def get_my_redemptions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's redemptions"""
    return db.query(models.Redemption).filter(
        models.Redemption.user_id == current_user.id
    ).order_by(models.Redemption.redeemed_at.desc()).all()

# ============== ADMIN ENDPOINTS ==============

@app.get("/users", response_model=list[schemas.UserResponse])
def get_all_users(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all users (for admin)"""
    return db.query(models.User).all()

@app.post("/admin/core-values", response_model=schemas.CoreValueResponse)
def admin_create_core_value(
    name: str,
    description: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new core value (admin)"""
    core_value = models.CoreValue(name=name, description=description)
    db.add(core_value)
    db.commit()
    db.refresh(core_value)
    return core_value

@app.delete("/admin/core-values/{core_value_id}")
def admin_delete_core_value(
    core_value_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete a core value (admin)"""
    core_value = db.query(models.CoreValue).filter(models.CoreValue.id == core_value_id).first()
    if not core_value:
        raise HTTPException(status_code=404, detail="Core value not found")
    db.delete(core_value)
    db.commit()
    return {"message": "Core value deleted"}

@app.post("/admin/rewards", response_model=schemas.RewardResponse)
def admin_create_reward(
    reward: schemas.RewardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new reward (admin)"""
    new_reward = models.Reward(
        name=reward.name,
        description=reward.description,
        point_cost=reward.point_cost
    )
    db.add(new_reward)
    db.commit()
    db.refresh(new_reward)
    return new_reward

@app.delete("/admin/rewards/{reward_id}")
def admin_delete_reward(
    reward_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete a reward (admin)"""
    reward = db.query(models.Reward).filter(models.Reward.id == reward_id).first()
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found")
    db.delete(reward)
    db.commit()
    return {"message": "Reward deleted"}

@app.patch("/admin/redemptions/{redemption_id}/fulfill")
def admin_fulfill_redemption(
    redemption_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Mark a redemption as fulfilled (admin)"""
    redemption = db.query(models.Redemption).filter(models.Redemption.id == redemption_id).first()
    if not redemption:
        raise HTTPException(status_code=404, detail="Redemption not found")
    redemption.status = "fulfilled"
    db.commit()
    return {"message": "Redemption fulfilled"}

@app.get("/admin/redemptions")
def admin_get_all_redemptions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all redemptions (admin)"""
    redemptions = db.query(models.Redemption).order_by(models.Redemption.redeemed_at.desc()).all()
    return redemptions
# ============== TEST ENDPOINT ==============

@app.get("/")
def read_root():
    return {"message": "Praise App API is running!"}