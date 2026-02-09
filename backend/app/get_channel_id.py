import httpx
import asyncio
import os

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # Or paste it directly for this one-time script

async def get_channels():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json={"types": "public_channel,private_channel"}
        )
        data = response.json()
        
        print("All channels:")
        for channel in data.get("channels", []):
            print(f"  #{channel['name']} → {channel['id']}")
            if channel["name"] == "meetings":
                print(f"\n✅ Found #meetings! ID: {channel['id']}")

asyncio.run(get_channels())