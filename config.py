import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///rufflife.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'app/static/uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    
    # Email Configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'rufflifenotifications@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'folnakxetwrskgue'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME') or 'rufflifenotifications@gmail.com'
    
    # Twilio SMS Configuration
    TWILIO_ACCOUNT_SID  = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN   = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

    # Staff phone numbers to receive forwarded customer replies
    STAFF_ALERT_PHONES = [
        '+19122390864',  # Ashley
        '+19126482295',  # Frances (Owner)
    ]

    # Support ticket SMS recipient
    SUPPORT_PHONE = '9128097600'

    # Business Info
    BUSINESS_NAME    = 'Ruff Life Retreat'
    BUSINESS_PHONE   = '(912) 648-2295'
    BUSINESS_ADDRESS = '2945 Midland Rd. Guyton, GA 31312'

    # AI Chat
    GROQ_API_KEY   = os.environ.get('GROQ_API_KEY', '')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # Pricing defaults (override in .env if needed)
    BOARDING_RATE_PRIMARY    = float(os.environ.get('BOARDING_RATE_PRIMARY',    40))
    BOARDING_RATE_ADDITIONAL = float(os.environ.get('BOARDING_RATE_ADDITIONAL', 25))
    DAYCARE_RATE_MULTI       = float(os.environ.get('DAYCARE_RATE_MULTI',       20))
    DAYCARE_RATE_SINGLE      = float(os.environ.get('DAYCARE_RATE_SINGLE',      25))
    ADDON_SPA_BATH_NAILS     = float(os.environ.get('ADDON_SPA_BATH_NAILS',     30))
    ADDON_SPA_BATH           = float(os.environ.get('ADDON_SPA_BATH',           30))
    ADDON_NAIL_TRIM          = float(os.environ.get('ADDON_NAIL_TRIM',          20))