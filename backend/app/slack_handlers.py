import re
import httpx
from datetime import datetime, timedelta
from .config import (
    SLACK_BOT_TOKEN,
    SLACK_WORKSPACE_DOMAIN,
    CHANNEL_TO_TRELLO_LIST,
    SLACK_TO_TRELLO_MEMBER,
    ALYANNA_BOARD_7DAY_LIST,
    L10VA_BOARD_7DAY_LIST,
    L10VA_CHANNEL_ID,
    MEETINGS_CHANNEL_ID_PIN,
    TRELLO_API_KEY,
    TRELLO_TOKEN,
)
from .alerts import send_alert
from .slack_helpers import (
    extract_full_message_content,
    get_channel_name,
    get_user_info,
)
from .trello_helpers import create_trello_card


async def handle_tta_message(event):
    """Handle TTA message - create Trello card in appropriate board"""
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    channel_name = await get_channel_name(channel_id)
    user_info = await get_user_info(user_id)
    user_real_name = user_info.get("real_name", "Unknown User")

    message_link = f"https://{SLACK_WORKSPACE_DOMAIN}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

    channel_config = CHANNEL_TO_TRELLO_LIST.get(channel_name, {})
    trello_list_id = channel_config.get("issues")

    if not trello_list_id:
        print(f"⚠️ No Trello board mapped for channel #{channel_name} - skipping")
        await send_alert("handle_tta_message", "No Trello board mapped for channel", {"Channel": channel_name})
        return

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


async def handle_announcement_message(event):
    """Handle announcement - create Trello card in announcement list"""
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    channel_name = await get_channel_name(channel_id)
    user_info = await get_user_info(user_id)
    user_real_name = user_info.get("real_name", "Unknown User")

    message_link = f"https://{SLACK_WORKSPACE_DOMAIN}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

    channel_config = CHANNEL_TO_TRELLO_LIST.get(channel_name, {})
    trello_list_id = channel_config.get("announcement")

    if not trello_list_id:
        print(f"⚠️ No announcement list mapped for channel #{channel_name} - skipping")
        await send_alert("handle_announcement_message", "No announcement list mapped for channel", {"Channel": channel_name})
        return

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
    """Handle TASK keyword in #l10-va - pins, creates Trello cards on two boards, DMs assignees"""
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    # Only process #l10-va
    if channel_id != L10VA_CHANNEL_ID:
        return

    message_link = f"https://{SLACK_WORKSPACE_DOMAIN}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

    # Extract tagged Slack users from raw text (before mention expansion)
    mentioned_users = re.findall(r"<@(U[A-Z0-9]+)>", event.get("text", ""))
    assigned_slack_ids = mentioned_users if mentioned_users else []
    assigned_trello_ids = [
        SLACK_TO_TRELLO_MEMBER[uid]
        for uid in assigned_slack_ids
        if uid in SLACK_TO_TRELLO_MEMBER
    ]

    # Get assigned users' names
    assigned_names = []
    for uid in assigned_slack_ids:
        user_info = await get_user_info(uid)
        name = user_info.get("real_name", "Unknown")
        assigned_names.append(name)

    assigned_names_str = ", ".join(assigned_names) if assigned_names else "Unassigned"

    # Get poster's name
    poster_info = await get_user_info(user_id)
    poster_name = poster_info.get("real_name", "Unknown")

    due_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT12:00:00.000Z")

    card_description = (
        f"**Assigned to:** {assigned_names_str}\n"
        f"**Posted by:** {poster_name}\n"
        f"**Slack message:** {message_link}\n\n"
        f"---\n\n"
        f"{original_text}"
    )

    async with httpx.AsyncClient() as client:
        # 1. Pin the message
        try:
            await client.post(
                "https://slack.com/api/pins.add",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": channel_id, "timestamp": timestamp}
            )
            print(f"📌 Pinned message in {channel_id}")
        except Exception as e:
            print(f"❌ Failed to pin message: {e}")
            await send_alert("handle_task_message", "Failed to pin message", {"Channel": channel_id, "Posted by": poster_name, "Error": str(e)})

        # 2. Create card on Alyanna's board
        alyanna_card_url = None
        try:
            card_data = {
                "key": TRELLO_API_KEY,
                "token": TRELLO_TOKEN,
                "idList": ALYANNA_BOARD_7DAY_LIST,
                "name": original_text[:80],
                "desc": card_description,
                "due": due_date,
            }
            if assigned_trello_ids:
                card_data["idMembers"] = assigned_trello_ids

            response = await client.post("https://api.trello.com/1/cards", params=card_data)
            alyanna_card = response.json()
            alyanna_card_url = alyanna_card.get("shortUrl")
            print(f"✅ Created card on Alyanna's board: {alyanna_card_url}")
        except Exception as e:
            print(f"❌ Failed to create Alyanna board card: {e}")
            await send_alert("handle_task_message", "Failed to create card on Alyanna's board", {"Assigned to": assigned_names_str, "Posted by": poster_name, "Error": str(e)})

        # 3. Create card on L10-VA board
        l10va_card_url = None
        try:
            card_data = {
                "key": TRELLO_API_KEY,
                "token": TRELLO_TOKEN,
                "idList": L10VA_BOARD_7DAY_LIST,
                "name": original_text[:80],
                "desc": card_description,
                "due": due_date,
            }
            if assigned_trello_ids:
                card_data["idMembers"] = assigned_trello_ids

            response = await client.post("https://api.trello.com/1/cards", params=card_data)
            l10va_card = response.json()
            l10va_card_url = l10va_card.get("shortUrl")
            print(f"✅ Created card on L10-VA board: {l10va_card_url}")
        except Exception as e:
            print(f"❌ Failed to create L10-VA board card: {e}")
            await send_alert("handle_task_message", "Failed to create card on L10-VA board", {"Assigned to": assigned_names_str, "Posted by": poster_name, "Error": str(e)})

        # 4. DM all assigned VAs
        for i, uid in enumerate(assigned_slack_ids):
            try:
                name = assigned_names[i] if i < len(assigned_names) else "there"
                dm_response = await client.post(
                    "https://slack.com/api/conversations.open",
                    headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                    json={"users": uid}
                )
                dm_channel = dm_response.json()["channel"]["id"]

                dm_text = (
                    f"👋 Hey {name}, you've been assigned a new task!\n\n"
                    f"*Task:* {original_text}\n"
                    f"*Posted by:* {poster_name}\n"
                    f"*Due:* 7 days from today\n\n"
                    f"*Slack message:* {message_link}\n"
                )
                if alyanna_card_url:
                    dm_text += f"*Alyanna's board:* {alyanna_card_url}\n"
                if l10va_card_url:
                    dm_text += f"*L10-VA board:* {l10va_card_url}\n"

                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                    json={"channel": dm_channel, "text": dm_text}
                )
                print(f"✅ DM sent to {name}")
            except Exception as e:
                print(f"❌ Failed to DM {uid}: {e}")
                await send_alert("handle_task_message", "Failed to DM assigned VA", {"VA Slack ID": uid, "Posted by": poster_name, "Error": str(e)})

        # 5. Reply in thread with Trello links
        try:
            reply_text = f"✅ Task created and assigned to {assigned_names_str}!\n"
            if alyanna_card_url:
                reply_text += f"📋 *Alyanna's Board:* {alyanna_card_url}\n"
            if l10va_card_url:
                reply_text += f"📋 *L10-VA Board:* {l10va_card_url}\n"

            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={
                    "channel": channel_id,
                    "thread_ts": timestamp,
                    "text": reply_text
                }
            )
            print(f"✅ Thread reply posted with Trello links")
        except Exception as e:
            print(f"❌ Failed to post thread reply: {e}")
            await send_alert("handle_task_message", "Failed to post thread reply", {"Channel": channel_id, "Posted by": poster_name, "Error": str(e)})


async def handle_meetings_pin(event):
    """Auto-pin top-level messages in #meetings (not thread replies)"""
    channel_id = event.get("channel")
    timestamp = event.get("ts")
    thread_ts = event.get("thread_ts")

    if channel_id != MEETINGS_CHANNEL_ID_PIN:
        return

    # Skip thread replies - only pin top-level messages
    if thread_ts and thread_ts != timestamp:
        return

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                "https://slack.com/api/pins.add",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": channel_id, "timestamp": timestamp}
            )
            print(f"📌 Auto-pinned message in #meetings")
        except Exception as e:
            print(f"❌ Failed to auto-pin in #meetings: {e}")
            await send_alert("handle_meetings_pin", "Failed to auto-pin message in #meetings", {"Error": str(e)})