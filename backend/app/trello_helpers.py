import asyncio
import httpx
from .config import TRELLO_API_KEY, TRELLO_TOKEN, SLACK_BOT_TOKEN
from .alerts import send_alert


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

    result = {}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.trello.com/1/cards",
                params={"key": TRELLO_API_KEY, "token": TRELLO_TOKEN},
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
            print(f"🔄 HEIC format detected, renaming to JPG")
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