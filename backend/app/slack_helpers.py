import re
import httpx
from .config import SLACK_BOT_TOKEN
from .alerts import send_alert


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
            await send_alert("expand_slack_mentions", "Failed to expand user mention", {"User ID": user_id, "Error": str(e)})

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
    """Extract full message text including forwarded content and images"""
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