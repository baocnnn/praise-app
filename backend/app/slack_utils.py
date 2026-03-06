from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from .config import SLACK_BOT_TOKEN

slack_client = WebClient(token=SLACK_BOT_TOKEN)

def get_user_by_slack_id(slack_user_id, db):
    """Get user from database by Slack ID"""
    from . import models
    return db.query(models.User).filter(models.User.slack_id == slack_user_id).first()

def get_slack_user_info(slack_user_id):
    """Get user info from Slack API"""
    try:
        response = slack_client.users_info(user=slack_user_id)
        return response["user"]
    except SlackApiError as e:
        print(f"Error getting user info: {e}")
        return None

def send_slack_message(channel, text):
    """Send a message to a Slack channel or user"""
    try:
        response = slack_client.chat_postMessage(
            channel=channel,
            text=text
        )
        return response
    except SlackApiError as e:
        print(f"Error sending message: {e}")
        return None

def parse_slack_user_id(text):
    """Extract user ID from Slack mention format <@U12345>"""
    if text.startswith("<@") and ">" in text:
        return text.split("<@")[1].split(">")[0].split("|")[0]
    return None

def get_slack_user_by_username(username):
    """Get Slack user ID by username"""
    try:
        # Remove @ if present
        username = username.lstrip('@')
        
        # Search for user by display name or real name
        response = slack_client.users_list()
        for user in response["members"]:
            if user.get("name") == username or user.get("profile", {}).get("display_name") == username:
                return user["id"]
        return None
    except SlackApiError as e:
        print(f"Error finding user: {e}")
        return None