import os
from dotenv import load_dotenv

load_dotenv()

APP_MODE = os.getenv("APP_MODE", "DEMO").upper()
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
DATABASE_PATH = os.getenv("DATABASE_PATH", "store.db")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
SUPPORTED_COUNTRIES = [
    "اليمن",
    "السودان",
    "ليبيا",
    "لبنان",
    "موريتانيا",
    "العراق",
    "سوريا",
    "جيبوتي",
    "الصومال",
]
