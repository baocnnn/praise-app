import os

# ============== SLACK ==============
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_WORKSPACE_DOMAIN = os.getenv("SLACK_WORKSPACE_DOMAIN", "apexdentalstudio")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# Channel IDs
MEETINGS_CHANNEL_ID = os.getenv("MEETINGS_CHANNEL_ID")
MEETINGS_CHANNEL_ID_PIN = "CHRTUSBUN"
L10VA_CHANNEL_ID = "C05DBULTCPQ"
BOT_ALERTS_CHANNEL_ID = "C0AJSBTE8MB"

# ============== TRELLO ==============
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

# VA Manager boards
ALYANNA_BOARD_7DAY_LIST = "69a1c609a64d8212fa549c39"
L10VA_BOARD_7DAY_LIST = "6386c669750f1a01644412c7"

# Channel → Trello list mapping
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

# ============== VA MAPPING ==============
# Slack User ID → Trello Member ID
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