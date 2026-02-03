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
    
    # DEBUG: Show what we received
    return {
        "response_type": "ephemeral",
        "text": f"DEBUG - Received text: `{text}`\n\nFirst 50 chars: `{text[:50]}`"
    }
    # Parse the command text
    # Expected format: <@U12345|user> "message" #core-value
    # Or: <@U12345> "message" #core-value
    
    # Extract receiver Slack ID from mention
    receiver_slack_id = None
    if text.startswith("<@"):
        # Find the end of the mention
        end_idx = text.find(">")
        if end_idx != -1:
            mention = text[2:end_idx]  # Remove <@ and >
            receiver_slack_id = mention.split("|")[0]  # Get ID before | if present
            text = text[end_idx+1:].strip()  # Remove mention from text
    
    if not receiver_slack_id:
        return {
            "response_type": "ephemeral",
            "text": "❌ Please mention a user. Usage: `/praise @user \"message\" #core-value`"
        }
    
    # Now parse message and core value from remaining text
    # Format should be: "message" #core-value
    if '"' not in text:
        return {
            "response_type": "ephemeral",
            "text": "❌ Please put your message in quotes. Usage: `/praise @user \"Your message\" #core-value`"
        }
    
    # Extract message between quotes
    parts = text.split('"')
    if len(parts) < 3:
        return {
            "response_type": "ephemeral",
            "text": "❌ Invalid format. Usage: `/praise @user \"Your message\" #core-value`"
        }
    
    message = parts[1]
    core_value_text = parts[2].strip()
    
    # Get receiver from database
    receiver = get_user_by_slack_id(receiver_slack_id, db)
    if not receiver:
        # Get their info from Slack to help create account
        slack_info = get_slack_user_info(receiver_slack_id)
        return {
            "response_type": "ephemeral",
            "text": f"❌ {slack_info['real_name'] if slack_info else 'This user'} hasn't registered yet. They need to sign up on the web app first."
        }
    
    # Can't praise yourself
    if giver.id == receiver.id:
        return {
            "response_type": "ephemeral",
            "text": "❌ You can't praise yourself!"
        }
    
    # Find core value by name (remove # if present)
    core_value_name = core_value_text.replace("#", "").strip()
    core_value = db.query(models.CoreValue).filter(
        models.CoreValue.name.ilike(f"%{core_value_name}%")
    ).first()
    
    if not core_value:
        available_values = db.query(models.CoreValue).all()
        values_list = ", ".join([f"#{cv.name.replace(' ', '')}" for cv in available_values])
        return {
            "response_type": "ephemeral",
            "text": f"❌ Core value not found. Available values: {values_list}"
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
    giver.points_balance += 5  # Giver gets 5 points
    
    db.add(new_praise)
    db.commit()
    
    # Send DM to receiver
    send_slack_message(
        receiver_slack_id,
        f"🎉 You received praise from {giver.first_name}!\n\n*{core_value.name}*\n\"{message}\"\n\n+{points_awarded} points"
    )
    
    return {
        "response_type": "in_channel",
        "text": f"🎉 {giver.first_name} praised {receiver.first_name} for *{core_value.name}*!\n\"{message}\"\n\n+{points_awarded} points to {receiver.first_name}, +5 points to {giver.first_name}"
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