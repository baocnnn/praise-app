from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from . import models
from .database import engine
from .slack_endpoints import router as slack_router
from .slack_handlers import (
    handle_task_message,
    handle_tta_message,
    handle_announcement_message,
    handle_meetings_pin,
)
from .routes import auth, praise, rewards, admin

# ============== APP SETUP ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(lifespan=lifespan)

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

# ============== ROUTERS ==============
app.include_router(slack_router)
app.include_router(auth.router)
app.include_router(praise.router)
app.include_router(rewards.router)
app.include_router(admin.router)

# ============== DEDUPLICATION ==============
processed_events = set()

# ============== SLACK EVENTS ==============

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

        await handle_meetings_pin(event)

    return {"ok": True}

# ============== HEALTH CHECK ==============

@app.get("/")
def read_root():
    return {"message": "Praise App API is running!"}