from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
import hashlib
import hmac
import time
from .database import get_db
from . import models
from .slack_utils import get_user_by_slack_id, get_slack_user_info, send_slack_message, parse_slack_user_id
from .slack_config import SLACK_SIGNING_SECRET

router = APIRouter()

def verify_slack_signature(request_body: bytes, timestamp: str, signature: str):
    """Verify that the request came from Slack"""
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    
    sig_basestring = f"v0:{timestamp}:{request_body.decode()}"
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)
@router.post("/slack/praise")
async def slack_praise_command(request: Request, db: Session = Depends(get_db)):
    """Handle /praise command from Slack"""
    from .slack_utils import get_slack_user_by_username
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify request is from Slack
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse form data
    form_data = await request.form()
    slack_user_id = form_data.get("user_id")
    text = form_data.get("text", "").strip()
    
    # Get giver from database
    giver = get_user_by_slack_id(slack_user_id, db)
    if not giver:
        return {
            "response_type": "ephemeral",
            "text": "❌ You need to link your Slack account first. Please register on the web app and we'll connect your account."
        }
    
    available_values = db.query(models.CoreValue).all()
    values_list = " or ".join([f"`{cv.name}`" for cv in available_values])
    # Parse the command text
    # Expected format: @username "message" #core-value
    
    # Extract message between quotes
    if not text.startswith("@"):
        return {
            "response_type": "ephemeral",
            "text": f"❌ Please start with @username\n\nExample: `/praise @User Great job today! #above`\n\nCore values: {values_list}"
        }
    parts = text.split(None, 1)  # Split on first space
    if len(parts) < 2:
        return {
            "response_type": "ephemeral",
            "text": f"❌ Please include a message\n\nExample: `/praise @julie.tellesc Great job! #above`"
        }
    
    username = parts[0][1:]  # Remove @
    rest_of_text = parts[1]
    
    # Find core value (look for # anywhere in the message)
    core_value = None
    message = rest_of_text
    
    if "#" in rest_of_text:
        # Split on last # to get the core value
        message_part, value_part = rest_of_text.rsplit("#", 1)
        message = message_part.strip()
        value_text = value_part.strip().lower().replace(" ", "")
        
        # Fuzzy match core values (ignore spaces and case)
        for cv in available_values:
            cv_normalized = cv.name.lower().replace(" ", "")
            # Match if the search term is in the core value name
            if value_text in cv_normalized or cv_normalized.startswith(value_text):
                core_value = cv
                break
    
    if not core_value:
        return {
            "response_type": "ephemeral",
            "text": f"❌ Please include a core value with #\n\nExample: `/praise @julie.tellesc Great job! #above`\n\nCore values: {values_list}"
        }
    
    if not message or len(message.strip()) < 3:
        return {
            "response_type": "ephemeral",
            "text": "❌ Please include a message about why you're giving praise"
        }
    
    # Clean up message (remove quotes if present)
    message = message.strip().strip('"').strip("'")
    
    # Look up Slack user ID by username
    receiver_slack_id = get_slack_user_by_username(username)
    
    if not receiver_slack_id:
        return {
            "response_type": "ephemeral",
            "text": f"❌ Could not find Slack user '@{username}'. Make sure the username is correct."
        }
    
    # Get receiver from database
    receiver = get_user_by_slack_id(receiver_slack_id, db)
    if not receiver:
        slack_info = get_slack_user_info(receiver_slack_id)
        return {
            "response_type": "ephemeral",
            "text": f"❌ {slack_info['real_name'] if slack_info else username} hasn't registered yet. They need to sign up on the web app first."
        }
    
    # Can't praise yourself
    if giver.id == receiver.id:
        return {
            "response_type": "ephemeral",
            "text": "❌ You can't praise yourself!"
        }
    
    # Create praise
    points_awarded = 10
    new_praise = models.Praise(
        giver_id=giver.id,
        receiver_id=receiver.id,
        message=message,
        core_value_id=core_value.id,
        points_awarded=points_awarded
    )
    
    # Update points
    receiver.points_balance += points_awarded
    giver.points_balance += 5
    
    db.add(new_praise)
    db.commit()
    
    # Send DM to receiver
    send_slack_message(
        receiver_slack_id,
        f"🎉 You received praise from {giver.first_name}!\n\n*{core_value.name}*\n\"{message}\"\n\n+{points_awarded} points"
    )
    
    return {
        "response_type": "in_channel",
        "text": f"🎉 {giver.first_name} praised {receiver.first_name} for *{core_value.name}*!\n\n\"{message}\"\n\n+{points_awarded} points to {receiver.first_name}, +5 points to {giver.first_name}"
    }

@router.post("/slack/my-praise")
async def slack_my_praise_command(request: Request, db: Session = Depends(get_db)):
    """Handle /my-praise command from Slack"""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    form_data = await request.form()
    slack_user_id = form_data.get("user_id")
    
    user = get_user_by_slack_id(slack_user_id, db)
    if not user:
        return {
            "response_type": "ephemeral",
            "text": "❌ You need to register on the web app first."
        }
    
    # Get user's praise
    praise_list = db.query(models.Praise).filter(
        models.Praise.receiver_id == user.id
    ).order_by(models.Praise.created_at.desc()).limit(5).all()
    
    if not praise_list:
        return {
            "response_type": "ephemeral",
            "text": "You haven't received any praise yet. Keep up the great work!"
        }
    
    # Format praise list
    praise_text = f"*Your Recent Praise ({len(praise_list)} shown):*\n\n"
    for p in praise_list:
        praise_text += f"• *{p.core_value.name}* from {p.giver.first_name}: \"{p.message}\" (+{p.points_awarded} pts)\n"
    
    return {
        "response_type": "ephemeral",
        "text": praise_text
    }

@router.post("/slack/my-points")
async def slack_my_points_command(request: Request, db: Session = Depends(get_db)):
    """Handle /my-points command from Slack"""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    form_data = await request.form()
    slack_user_id = form_data.get("user_id")
    
    user = get_user_by_slack_id(slack_user_id, db)
    if not user:
        return {
            "response_type": "ephemeral",
            "text": "❌ You need to register on the web app first."
        }
    
    return {
        "response_type": "ephemeral",
        "text": f"💰 You have *{user.points_balance} points*!"
    }