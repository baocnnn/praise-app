import httpx
import asyncio
import os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta
from contextlib import asynccontextmanager
from . import models, schemas, auth
from .database import engine, get_db
from .slack_endpoints import router as slack_router


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
        "https://apex-kudos-app.web.app",
        "https://apex-kudos-app.firebaseapp.com",  
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(slack_router)

MEETINGS_CHANNEL_ID = os.getenv("MEETINGS_CHANNEL_ID")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

CHANNEL_TO_TRELLO_LIST = {
    "providers": {
        "issues": "6483543ec44e0f245fae9002"
    },
    "frontoffice": {
        "issues":       "61e2179fcbf1fe646e85cf69",
        "announcement": "61e2173c83bddb327ec93d4d",
        "task":         "61e2174a3d5379613e67a5bb"
    },
    "hygienist": {
        "issues": "617431ba61c5c56bedea397c"
    },
    "assistants": {
        "issues": "61e214aaf219b71c221944f4"
    },
    "hygiene": {
        "issues": "61e214aaf219b71c221944f4"
    },
    "l10-va": {
        "issues": "6386c669750f1a01644412ca"
    },
}

processed_events = set()
async def expand_slack_mentions(text, client=None):
    """Convert Slack mentions to readable names (without @ to avoid Trello mentions)"""
    import re
    
    if client is None:
        client = httpx.AsyncClient()
        close_client = True
    else:
        close_client = False
    
    # Find all user mentions: <@U12345>
    user_mentions = re.findall(r'<@(U[A-Z0-9]+)>', text)
    for user_id in user_mentions:
        try:
            response = await client.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                params={"user": user_id}
            )
            data = response.json()
            if data.get("ok"):
                name = data.get("user", {}).get("real_name", user_id)
                text = text.replace(f"<@{user_id}>", name)  # Changed from f"@{name}"
        except:
            pass
    
    # Find all usergroup mentions: <!subteam^S12345>
    group_mentions = re.findall(r'<!subteam\^([A-Z0-9]+)>', text)
    for group_id in group_mentions:
        try:
            response = await client.get(
                "https://slack.com/api/usergroups.info",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                params={"usergroup": group_id}
            )
            data = response.json()
            if data.get("ok"):
                handle = data.get("usergroup", {}).get("handle", group_id)
                text = text.replace(f"<!subteam^{group_id}>", handle)  # Changed from f"@{handle}"
        except:
            pass
    
    # Clean up other special mentions (remove @ symbol)
    text = text.replace("<!channel>", "channel")
    text = text.replace("<!here>", "here")
    text = text.replace("<!everyone>", "everyone")
    
    if close_client:
        await client.aclose()
    
    return text
 
async def extract_full_message_content(event):
    
    original_text = event.get("text", "")
    images_to_attach = []
    
    # Expand mentions first
    original_text = await expand_slack_mentions(original_text)
    
    # Check for forwarded messages (attachments)
    attachments = event.get("attachments", [])
    
    async with httpx.AsyncClient() as client:
        for attachment in attachments:
            # Handle message shares - need to fetch the actual message
            if attachment.get("is_msg_unfurl") or attachment.get("is_share"):
                # Extract channel and timestamp from the attachment
                # Format: "Posted in <#CHANNEL_ID|channel-name>"
                from_channel = attachment.get("channel_id") or attachment.get("from_channel")
                msg_ts = attachment.get("ts")
                
                # If we have both, fetch the actual message
                if from_channel and msg_ts:
                    try:
                        response = await client.get(
                            "https://slack.com/api/conversations.history",
                            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                            params={
                                "channel": from_channel,
                                "latest": msg_ts,
                                "inclusive": True,
                                "limit": 1
                            }
                        )
                        data = response.json()
                        
                        if data.get("ok") and data.get("messages"):
                            shared_msg = data["messages"][0]
                            shared_text = shared_msg.get("text", "")
                            
                            # Expand mentions in the shared message
                            shared_text = await expand_slack_mentions(shared_text)
                            
                            # Get author info
                            author_id = shared_msg.get("user")
                            if author_id:
                                user_response = await client.get(
                                    "https://slack.com/api/users.info",
                                    headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                                    params={"user": author_id}
                                )
                                user_data = user_response.json()
                                if user_data.get("ok"):
                                    author_name = user_data.get("user", {}).get("real_name", "Unknown")
                                    original_text += f"\n\n**Forwarded from {author_name}:**\n{shared_text}"
                                else:
                                    original_text += f"\n\n**Forwarded message:**\n{shared_text}"
                            else:
                                original_text += f"\n\n**Forwarded message:**\n{shared_text}"
                            
                            # Check for images in the shared message
                            shared_files = shared_msg.get("files", [])
                            for file in shared_files:
                                if file.get("mimetype", "").startswith("image/"):
                                    images_to_attach.append({
                                        "url_private": file.get("url_private"),
                                        "name": file.get("name", "shared_image.jpg"),
                                        "mimetype": file.get("mimetype", "image/jpeg")
                                    })
                    except Exception as e:
                        print(f"⚠️ Failed to fetch shared message: {e}")
                        # Fall back to attachment text if fetch fails
                        att_text = attachment.get("text", "") or attachment.get("fallback", "")
                        if att_text:
                            att_text = await expand_slack_mentions(att_text)
                            original_text += f"\n\n**Forwarded message:**\n{att_text}"
                
                # Check for images in the attachment itself
                if attachment.get("image_url"):
                    images_to_attach.append({
                        "url_private": attachment.get("image_url"),
                        "name": "forwarded_image.jpg",
                        "mimetype": "image/jpeg"
                    })
            
            # Handle regular attachments (non-shares)
            elif attachment.get("text"):
                att_text = attachment.get("text", "")
                att_text = await expand_slack_mentions(att_text)
                original_text += f"\n\n{att_text}"
                
                if attachment.get("image_url"):
                    images_to_attach.append({
                        "url_private": attachment.get("image_url"),
                        "name": "attachment_image.jpg",
                        "mimetype": "image/jpeg"
                    })
    
    # Check for direct file shares
    files = event.get("files", [])
    for file in files:
        if file.get("preview"):
            original_text += f"\n\n**File preview:**\n{file.get('preview')}"
    
    # Final cleanup
    import re
    original_text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', original_text)
    original_text = re.sub(r'<(https?://[^>]+)>', r'\1', original_text)
    
    return original_text, images_to_attach
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

@app.patch("/me/link-slack")
def link_slack_account(
    slack_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Link Slack account to user"""
    # Check if slack_id is already used
    existing = db.query(models.User).filter(models.User.slack_id == slack_id).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="This Slack account is already linked")
    
    current_user.slack_id = slack_id
    db.commit()
    return {"message": "Slack account linked successfully"}
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
    from sqlalchemy.orm import joinedload
    
    redemptions = db.query(models.Redemption).options(
        joinedload(models.Redemption.reward),
        joinedload(models.Redemption.user)
    ).order_by(models.Redemption.redeemed_at.desc()).all()
    
    return redemptions

@app.post("/slack/events")
async def slack_events(request: Request):
    data = await request.json()

    # URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    if data.get("type") == "event_callback":
        event = data["event"]

        # Ignore bot messages to prevent loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"ok": True}

        # Deduplicate events using event_id
        event_id = data.get("event_id")
        if event_id in processed_events:
            print(f"⚠️ Duplicate event {event_id} - skipping")
            return {"ok": True}

        # Mark event as processed
        processed_events.add(event_id)

        # Keep set from growing too large
        if len(processed_events) > 1000:
            processed_events.clear()

    message_text = event.get("text", "").upper()

    # Priority order: Task > Announcement > TTA
    if message_text.startswith("TASK"):
        await handle_task_message(event)
    elif "ANNOUNCEMENT" in message_text or "ANNOUCEMENT" in message_text:
        await handle_announcement_message(event)
    elif message_text.startswith("TTA"):
        await handle_tta_message(event)

        return {"ok": True}


async def handle_tta_message(event):
    """Handle TTA message - create Trello card in appropriate board"""
    # Get full message content including forwards
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    channel_name = await get_channel_name(channel_id)
    user_info = await get_user_info(user_id)
    user_real_name = user_info.get("real_name", "Unknown User")

    workspace_domain = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
    message_link = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

    # Look up issues list for this channel
    channel_config = CHANNEL_TO_TRELLO_LIST.get(channel_name, {})
    trello_list_id = channel_config.get("issues")

    if not trello_list_id:
        print(f"⚠️ No Trello board mapped for channel #{channel_name} - skipping")
        return

    # Collect both direct images and forwarded images
    files = event.get("files", [])
    direct_images = [f for f in files if f.get("mimetype", "").startswith("image/")]
    all_images = direct_images + forwarded_images
    
    print(f"📎 Found {len(all_images)} image(s) attached to TTA message")

    await create_trello_card(
        list_id=trello_list_id,
        channel_name=channel_name,
        user_name=user_real_name,
        message=original_text,
        slack_link=message_link,
        images=all_images,
        card_type="TTA"
    )

async def create_trello_card(list_id, channel_name, user_name, message, slack_link, images=None, card_type="TTA"):
    """Create a Trello card in the specified list"""

    # Card title: first 50 chars of message
    title = message[:50] + "..." if len(message) > 50 else message

    # Card description
    description = f"""**Type:** {card_type}
**Posted by:** {user_name}
**Channel:** #{channel_name}

**Message:**
{message}

---
[🔗 View original Slack message]({slack_link})"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.trello.com/1/cards",
            params={
                "key": TRELLO_API_KEY,
                "token": TRELLO_TOKEN
            },
            json={
                "idList": list_id,
                "name": title,
                "desc": description,
                "pos": "top"
            }
        )
        result = response.json()

        if not result.get("id"):
            print(f"❌ Failed to create Trello card: {result}")
            return result

        card_id = result.get("id")
        card_url = result.get("url", "")
        print(f"✅ Trello {card_type} card created in #{channel_name} board: {card_url}")

        if images:
            for image in images:
                await attach_image_to_card(client, card_id, image)

    return result

async def attach_image_to_card(client, card_id, image):
    """Download image from Slack and upload to Trello card"""
    image_url = image.get("url_private")
    image_name = image.get("name", "attachment.jpg")
    mimetype = image.get("mimetype", "image/jpeg")

    if not image_url:
        print(f"⚠️ No URL found for image {image_name}")
        return

    try:
        # Retry logic - wait for image to be available
        max_retries = 5
        retry_delay = 2
        image_data = None

        for attempt in range(max_retries):
            print(f"⬇️ Attempting to download {image_name} (attempt {attempt + 1}/{max_retries})...")

            image_response = await client.get(
                image_url,
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                follow_redirects=True,
                timeout=30.0
            )

            content_type = image_response.headers.get("content-type", "")
            content_length = len(image_response.content)

            print(f"📥 Status: {image_response.status_code} | Content-Type: {content_type} | Size: {content_length} bytes")

            if (
                image_response.status_code == 200
                and content_length > 1000
                and "image" in content_type
            ):
                image_data = image_response.content
                print(f"✅ Successfully downloaded {image_name} ({content_length} bytes)")
                break
            else:
                if attempt < max_retries - 1:
                    print(f"⏳ Image not ready yet, waiting {retry_delay} seconds before retry...")
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"❌ Image never became available after {max_retries} attempts")
                    return

        if not image_data:
            print(f"❌ Failed to get image data for {image_name}")
            return

        # Handle HEIC format
        if image_name.upper().endswith('.HEIC'):
            print(f"🔄 HEIC format detected, renaming to JPG for compatibility")
            image_name = image_name.rsplit('.', 1)[0] + '.jpg'
            mimetype = 'image/jpeg'

        # Upload to Trello
        print(f"⬆️ Uploading {image_name} to Trello card...")
        upload_response = await client.post(
            f"https://api.trello.com/1/cards/{card_id}/attachments",
            params={
                "key": TRELLO_API_KEY,
                "token": TRELLO_TOKEN
            },
            files={
                "file": (image_name, image_data, mimetype)
            },
            timeout=30.0
        )

        upload_result = upload_response.json()

        if upload_result.get("id"):
            print(f"✅ Image attached to Trello card: {image_name}")
        else:
            print(f"❌ Failed to attach image: {upload_result}")

    except Exception as e:
        print(f"❌ Error attaching image: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()



async def get_channel_name(channel_id):
    """Get channel name from ID"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://slack.com/api/conversations.info",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"channel": channel_id}
        )
        data = response.json()

        if not data.get("ok"):
            print(f"❌ Failed to get channel info: {data.get('error')} for channel {channel_id}")
            return "unknown-channel"

        return data.get("channel", {}).get("name", "unknown-channel")


async def get_user_info(user_id):
    """Get user details from Slack"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"user": user_id}
        )
        data = response.json()

        if not data.get("ok"):
            print(f"❌ Failed to get user info: {data.get('error')} for user {user_id}")
            return {}

        user_data = data.get("user", {})
        print(f"✅ Got user info for: {user_data.get('real_name', 'Unknown')}")
        return user_data



async def post_to_slack(channel_id, text=None, blocks=None):
    """Post message to Slack channel"""
    async with httpx.AsyncClient() as client:
        payload = {
            "channel": channel_id,
            "unfurl_links": False
        }

        if blocks:
            payload["blocks"] = blocks
        if text:
            payload["text"] = text

        response = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json=payload
        )
        return response.json()
    
async def handle_announcement_message(event):
    """Handle announcement - only for #frontoffice channel"""
    # Get full message content including forwards
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    channel_name = await get_channel_name(channel_id)
    user_info = await get_user_info(user_id)
    user_real_name = user_info.get("real_name", "Unknown User")

    workspace_domain = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
    message_link = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

    # Look up announcement list for this channel
    channel_config = CHANNEL_TO_TRELLO_LIST.get(channel_name, {})
    trello_list_id = channel_config.get("announcement")

    if not trello_list_id:
        print(f"⚠️ No announcement list mapped for channel #{channel_name} - skipping")
        return

    # Collect both direct images and forwarded images
    files = event.get("files", [])
    direct_images = [f for f in files if f.get("mimetype", "").startswith("image/")]
    all_images = direct_images + forwarded_images
    
    print(f"📎 Found {len(all_images)} image(s) attached to announcement")

    await create_trello_card(
        list_id=trello_list_id,
        channel_name=channel_name,
        user_name=user_real_name,
        message=original_text,
        slack_link=message_link,
        images=all_images,
        card_type="Announcement"
    )
async def handle_task_message(event):
    # Get full message content including forwards
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    channel_name = await get_channel_name(channel_id)
    user_info = await get_user_info(user_id)
    user_real_name = user_info.get("real_name", "Unknown User")

    workspace_domain = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
    message_link = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

    # Look up task list for this channel
    channel_config = CHANNEL_TO_TRELLO_LIST.get(channel_name, {})
    trello_list_id = channel_config.get("task")

    if not trello_list_id:
        print(f"⚠️ No task list mapped for channel #{channel_name} - skipping")
        return

    # Collect both direct images and forwarded images
    files = event.get("files", [])
    direct_images = [f for f in files if f.get("mimetype", "").startswith("image/")]
    all_images = direct_images + forwarded_images
    
    print(f"📎 Found {len(all_images)} image(s) attached to task")

    await create_trello_card(
        list_id=trello_list_id,
        channel_name=channel_name,
        user_name=user_real_name,
        message=original_text,
        slack_link=message_link,
        images=all_images,
        card_type="Task"
    )
# ============== TEST ENDPOINT ==============

@app.get("/")
def read_root():
    return {"message": "Praise App API is running!"}