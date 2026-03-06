import httpx
from .config import SLACK_BOT_TOKEN, BOT_ALERTS_CHANNEL_ID


async def send_alert(function_name: str, error: str, context: dict = {}):
    """Send error alert to #bot-alerts channel"""
    context_lines = "\n".join([f"*{k}:* {v}" for k, v in context.items()])
    alert_text = (
        f"🚨 *Bot Alert*\n"
        f"*Function:* {function_name}\n"
        f"*Error:* {error}\n"
        f"{context_lines}"
    )
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": BOT_ALERTS_CHANNEL_ID, "text": alert_text}
            )
    except Exception as e:
        print(f"❌ Failed to send alert: {e}")