import httpx
import asyncio
import os
import re
from datetime import datetime, timedelta
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

# ============== ENVIRONMENT VARIABLES ==============
MEETINGS_CHANNEL_ID = os.getenv("MEETINGS_CHANNEL_ID")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

# ============== TRELLO CHANNEL MAPPING ==============
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
        "issues":       "6386c669750f1a01644412ca",
        "announcement": "6904a90c83a278e8ad4648b7"
    },
}

# ============== TASK FEATURE - VA MAPPING ==============
ALYANNA_BOARD_7DAY_LIST = "68c8f0f36f3f26219628f3a6"
L10VA_BOARD_7DAY_LIST = "6386c669750f1a01644412c7"
L10VA_CHANNEL_ID = "C05DBULTCPQ"
MEETINGS_CHANNEL_ID_PIN = "CHRTUSBUN"
BOT_ALERTS_CHANNEL_ID = "C0AJSBTE8MB"

SLACK_TO_TRELLO_MEMBER = {
    "U01FV8EJH5X": "5f5a2ad4ad395a6c4a5f9549",  # Alyanna
    "U028Z1MMW91": "60fa4c2c92ade57245d67e4b",  # DJ (Desiree)
    "U070MPN1WG6": "662ceeb35e686be0b33a7f1f",  # May (Menchie)
    "U038FJ67Q1Z": "623c644e5bc27f7f418b5e82",  # Aryn
    "U04RSMLR6QY": "63fcd1d7f63be895c0573505",  # Estela
    "U052CQVKK7F": "64340aac8ddff85487c64171",  # Jorina
    "U02HT479V9A": "6167a68957befe8a20f8d545",  # Aizel
    "U03RBQ5DNRF": "62df76044c937e2d2da1435c",  # April
    "U05QA6H27QV": "64f876f47e37df3293d09913",  # Erika
    "U04JQU58YHF": "5baf7b9bd776ff36f227125a",  # Junilyn
    "U026A1SKFMY": "60d94ad9e8b73e22772690d9",  # Jessa
}

processed_events = set()

# ============== ALERT HELPER ==============

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

# ============== SLACK HELPER FUNCTIONS ==============

async def expand_slack_mentions(text, client=None):
    """Convert Slack mentions to readable names"""
    if client is None:
        client = httpx.AsyncClient()
        close_client = True
    else:
        close_client = False

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
                text = text.replace(f"<@{user_id}>", name)
        except Exception as e:
            print(f"❌ Error expanding user mention: {e}")
            await send_alert("expand_slack_mentions", f"Failed to expand user mention", {"User ID": user_id, "Error": str(e)})

    group_mentions = re.findall(r'<!subteam\^([A-Z0-9]+)>', text)
    if group_mentions:
        try:
            response = await client.get(
                "https://slack.com/api/usergroups.list",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
            )
            data = response.json()
            if data.get("ok"):
                usergroups = data.get("usergroups", [])
                group_lookup = {ug["id"]: ug.get("handle", ug["id"]) for ug in usergroups}
                for group_id in group_mentions:
                    if group_id in group_lookup:
                        handle = group_lookup[group_id]
                        text = text.replace(f"<!subteam^{group_id}>", handle)
                        print(f"✅ Replaced usergroup {group_id} with {handle}")
                    else:
                        print(f"⚠️ Usergroup {group_id} not found in list")
            else:
                print(f"❌ Failed to list usergroups: {data.get('error')}")
                await send_alert("expand_slack_mentions", "Failed to list usergroups", {"Error": data.get('error')})
        except Exception as e:
            print(f"❌ Error expanding usergroup mentions: {e}")
            await send_alert("expand_slack_mentions", "Exception expanding usergroup mentions", {"Error": str(e)})

    text = text.replace("<!channel>", "channel")
    text = text.replace("<!here>", "here")
    text = text.replace("<!everyone>", "everyone")

    if close_client:
        await client.aclose()

    return text


async def extract_full_message_content(event):
    original_text = event.get("text", "")
    images_to_attach = []

    original_text = await expand_slack_mentions(original_text)

    attachments = event.get("attachments", [])

    async with httpx.AsyncClient() as client:
        for attachment in attachments:
            if attachment.get("is_msg_unfurl") or attachment.get("is_share"):
                from_channel = attachment.get("channel_id") or attachment.get("from_channel")
                msg_ts = attachment.get("ts")

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
                            shared_text = await expand_slack_mentions(shared_text)

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
                        await send_alert("extract_full_message_content", "Failed to fetch shared message", {"Channel": from_channel, "Error": str(e)})
                        att_text = attachment.get("text", "") or attachment.get("fallback", "")
                        if att_text:
                            att_text = await expand_slack_mentions(att_text)
                            original_text += f"\n\n**Forwarded message:**\n{att_text}"

                if attachment.get("image_url"):
                    images_to_attach.append({
                        "url_private": attachment.get("image_url"),
                        "name": "forwarded_image.jpg",
                        "mimetype": "image/jpeg"
                    })

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

    files = event.get("files", [])
    for file in files:
        if file.get("preview"):
            original_text += f"\n\n**File preview:**\n{file.get('preview')}"

    original_text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', original_text)
    original_text = re.sub(r'<(https?://[^>]+)>', r'\1', original_text)

    return original_text, images_to_attach


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
            await send_alert("get_channel_name", "Failed to get channel info", {"Channel ID": channel_id, "Error": data.get('error')})
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
            await send_alert("get_user_info", "Failed to get user info", {"User ID": user_id, "Error": data.get('error')})
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

# ============== TRELLO HELPER FUNCTIONS ==============

async def create_trello_card(list_id, channel_name, user_name, message, slack_link, images=None, card_type="TTA"):
    """Create a Trello card in the specified list"""
    title = message[:50] + "..." if len(message) > 50 else message

    description = f"""**Type:** {card_type}
**Posted by:** {user_name}
**Channel:** #{channel_name}

**Message:**
{message}

---
[🔗 View original Slack message]({slack_link})"""

    async with httpx.AsyncClient() as client:
        try:
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
                await send_alert("create_trello_card", "Failed to create Trello card", {"Channel": channel_name, "Type": card_type, "Error": str(result)})
                return result

            card_id = result.get("id")
            card_url = result.get("url", "")
            print(f"✅ Trello {card_type} card created in #{channel_name} board: {card_url}")

            if images:
                for image in images:
                    await attach_image_to_card(client, card_id, image)

        except Exception as e:
            print(f"❌ Exception creating Trello card: {e}")
            await send_alert("create_trello_card", "Exception creating Trello card", {"Channel": channel_name, "Type": card_type, "Error": str(e)})

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
                    await send_alert("attach_image_to_card", "Image never became available after max retries", {"Image": image_name, "Card ID": card_id})
                    return

        if not image_data:
            return

        if image_name.upper().endswith('.HEIC'):
            print(f"🔄 HEIC format detected, renaming to JPG for compatibility")
            image_name = image_name.rsplit('.', 1)[0] + '.jpg'
            mimetype = 'image/jpeg'

        print(f"⬆️ Uploading {image_name} to Trello card...")
        upload_response = await client.post(
            f"https://api.trello.com/1/cards/{card_id}/attachments",
            params={"key": TRELLO_API_KEY, "token": TRELLO_TOKEN},
            files={"file": (image_name, image_data, mimetype)},
            timeout=30.0
        )

        upload_result = upload_response.json()
        if upload_result.get("id"):
            print(f"✅ Image attached to Trello card: {image_name}")
        else:
            print(f"❌ Failed to attach image: {upload_result}")
            await send_alert("attach_image_to_card", "Failed to attach image to Trello card", {"Image": image_name, "Card ID": card_id, "Error": str(upload_result)})

    except Exception as e:
        print(f"❌ Error attaching image: {type(e).__name__}: {e}")
        await send_alert("attach_image_to_card", "Exception attaching image", {"Image": image_name, "Card ID": card_id, "Error": str(e)})

# ============== MESSAGE HANDLERS ==============

async def handle_tta_message(event):
    """Handle TTA message - create Trello card in appropriate board"""
    original_text, forwarded_images = await extract_full_message_content(event)
    user_id = event.get("user")
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    channel_name = await get_channel_name(channel_id)
    user_info = await get_user_info(user_id)
    user_real_name = user_info.get("real_name", "Unknown User")

    workspace_domain = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
    message_link = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

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

    workspace_domain = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
    message_link = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

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

    workspace_domain = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
    message_link = f"https://{workspace_domain}.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}"

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
    """Auto-pin every message posted in #meetings"""
    channel_id = event.get("channel")
    timestamp = event.get("ts")

    if channel_id != MEETINGS_CHANNEL_ID_PIN:
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

# ============== SLACK EVENTS ENDPOINT ==============

@app.post("/slack/events")
async def slack_events(request: Request):
    data = await request.json()

    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    if data.get("type") == "event_callback":
        event = data["event"]

        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"ok": True}

        event_id = data.get("event_id")
        if event_id in processed_events:
            print(f"⚠️ Duplicate event {event_id} - skipping")
            return {"ok": True}

        processed_events.add(event_id)

        if len(processed_events) > 1000:
            processed_events.clear()

        message_text = event.get("text", "").upper()

        if message_text.startswith("TASK"):
            await handle_task_message(event)
        elif "ANNOUNCEMENT" in message_text or "ANNOUCEMENT" in message_text:
            await handle_announcement_message(event)
        elif message_text.startswith("TTA"):
            await handle_tta_message(event)

        # Auto-pin #meetings regardless of keyword
        await handle_meetings_pin(event)

    return {"ok": True}

# ============== AUTHENTICATION ENDPOINTS ==============

@app.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
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
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/token", response_model=schemas.Token)
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.patch("/me/link-slack")
def link_slack_account(
    slack_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    existing = db.query(models.User).filter(models.User.slack_id == slack_id).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="This Slack account is already linked")
    current_user.slack_id = slack_id
    db.commit()
    return {"message": "Slack account linked successfully"}

# ============== CORE VALUES ENDPOINTS ==============

@app.post("/core-values")
def create_core_value(name: str, description: str = "", db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    core_value = models.CoreValue(name=name, description=description)
    db.add(core_value)
    db.commit()
    db.refresh(core_value)
    return core_value


@app.get("/core-values")
def get_core_values(db: Session = Depends(get_db)):
    return db.query(models.CoreValue).all()

# ============== PRAISE ENDPOINTS ==============

@app.post("/praise", response_model=schemas.PraiseResponse)
def give_praise(praise: schemas.PraiseCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
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


@app.get("/praise", response_model=list[schemas.PraiseResponse])
def get_all_praise(db: Session = Depends(get_db)):
    return db.query(models.Praise).order_by(models.Praise.created_at.desc()).all()


@app.get("/praise/received", response_model=list[schemas.PraiseResponse])
def get_my_praise(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Praise).filter(
        models.Praise.receiver_id == current_user.id
    ).order_by(models.Praise.created_at.desc()).all()

# ============== REWARDS ENDPOINTS ==============

@app.post("/rewards", response_model=schemas.RewardResponse)
def create_reward(reward: schemas.RewardCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    new_reward = models.Reward(name=reward.name, description=reward.description, point_cost=reward.point_cost)
    db.add(new_reward)
    db.commit()
    db.refresh(new_reward)
    return new_reward


@app.get("/rewards", response_model=list[schemas.RewardResponse])
def get_rewards(db: Session = Depends(get_db)):
    return db.query(models.Reward).filter(models.Reward.is_active == True).all()


@app.post("/redeem", response_model=schemas.RedemptionResponse)
def redeem_reward(redemption: schemas.RedemptionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
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


@app.get("/my-redemptions", response_model=list[schemas.RedemptionResponse])
def get_my_redemptions(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Redemption).filter(
        models.Redemption.user_id == current_user.id
    ).order_by(models.Redemption.redeemed_at.desc()).all()

# ============== ADMIN ENDPOINTS ==============

@app.get("/users", response_model=list[schemas.UserResponse])
def get_all_users(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.User).all()


@app.post("/admin/core-values", response_model=schemas.CoreValueResponse)
def admin_create_core_value(name: str, description: str = "", db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    core_value = models.CoreValue(name=name, description=description)
    db.add(core_value)
    db.commit()
    db.refresh(core_value)
    return core_value


@app.delete("/admin/core-values/{core_value_id}")
def admin_delete_core_value(core_value_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    core_value = db.query(models.CoreValue).filter(models.CoreValue.id == core_value_id).first()
    if not core_value:
        raise HTTPException(status_code=404, detail="Core value not found")
    db.delete(core_value)
    db.commit()
    return {"message": "Core value deleted"}


@app.post("/admin/rewards", response_model=schemas.RewardResponse)
def admin_create_reward(reward: schemas.RewardCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    new_reward = models.Reward(name=reward.name, description=reward.description, point_cost=reward.point_cost)
    db.add(new_reward)
    db.commit()
    db.refresh(new_reward)
    return new_reward


@app.delete("/admin/rewards/{reward_id}")
def admin_delete_reward(reward_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    reward = db.query(models.Reward).filter(models.Reward.id == reward_id).first()
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found")
    db.delete(reward)
    db.commit()
    return {"message": "Reward deleted"}


@app.patch("/admin/redemptions/{redemption_id}/fulfill")
def admin_fulfill_redemption(redemption_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    redemption = db.query(models.Redemption).filter(models.Redemption.id == redemption_id).first()
    if not redemption:
        raise HTTPException(status_code=404, detail="Redemption not found")
    redemption.status = "fulfilled"
    db.commit()
    return {"message": "Redemption fulfilled"}


@app.get("/admin/redemptions")
def admin_get_all_redemptions(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    from sqlalchemy.orm import joinedload
    redemptions = db.query(models.Redemption).options(
        joinedload(models.Redemption.reward),
        joinedload(models.Redemption.user)
    ).order_by(models.Redemption.redeemed_at.desc()).all()
    return redemptions

# ============== TEST ENDPOINT ==============

@app.get("/")
def read_root():
    return {"message": "Praise App API is running!"}