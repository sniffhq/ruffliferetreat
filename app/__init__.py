import json as _json
from datetime import datetime as _datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from config import Config

db            = SQLAlchemy()
login_manager = LoginManager()
migrate       = Migrate()
mail          = Mail()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # ── SQLite WAL mode ───────────────────────────────────────────────────────
    # WAL (Write-Ahead Logging) lets readers and writers run concurrently
    # instead of blocking each other, eliminating "Loading…" hangs on kennel
    # dropdowns and other AJAX calls when a write is in progress.
    from sqlalchemy import event
    @event.listens_for(db.engine, 'connect')
    def _set_sqlite_wal(dbapi_conn, _rec):
        try:
            dbapi_conn.execute('PRAGMA journal_mode=WAL')
            dbapi_conn.execute('PRAGMA synchronous=NORMAL')  # safe + faster with WAL
        except Exception:
            pass  # non-SQLite databases ignore this silently

    login_manager.login_view              = 'auth.login'
    login_manager.login_message           = 'Please log in to access this page.'
    login_manager.login_message_category  = 'info'

    # ── Brand context processor ───────────────────────────────────────────────
    @app.context_processor
    def inject_brand():
        # Unread SMS count for nav badge — only when user is logged in
        unread_sms_count = 0
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated and getattr(current_user, 'is_admin', False):
                from app.models import SmsMessage
                unread_sms_count = SmsMessage.query.filter_by(
                    direction='inbound', read=False
                ).count()
        except Exception:
            pass

        return {
            'unread_sms_count': unread_sms_count,
            'brand': {
                'name':         app.config.get('BUSINESS_NAME',      'Ruff Life Retreat'),
                'tagline':      app.config.get('BUSINESS_TAGLINE',   'Premium Boarding, Grooming & Daycare'),
                'phone':        app.config.get('BUSINESS_PHONE',     ''),
                'address':      app.config.get('BUSINESS_ADDRESS',   ''),
                'domain':       app.config.get('BUSINESS_DOMAIN',    ''),
                'email':        app.config.get('BUSINESS_EMAIL',     ''),
                'primary':      app.config.get('BRAND_PRIMARY',      '#1B2A4A'),
                'accent':       app.config.get('BRAND_ACCENT',       '#B07A8E'),
                'accent_light': app.config.get('BRAND_ACCENT_LIGHT', '#C9A0AF'),
                'accent_pale':  app.config.get('BRAND_ACCENT_PALE',  '#F5EAF0'),
                'accent_dark':  app.config.get('BRAND_ACCENT_DARK',  '#9A6070'),
                'logo':         app.config.get('BRAND_LOGO',         'logo.png'),
            },
            'features': {
                'daycare':      app.config.get('FEATURE_DAYCARE',      True),
                'grooming':     app.config.get('FEATURE_GROOMING',     True),
                'gallery':      app.config.get('FEATURE_GALLERY',      True),
                'kiosk':        app.config.get('FEATURE_KIOSK',        True),
                'report_cards': app.config.get('FEATURE_REPORT_CARDS', True),
            },
            'pricing': {
                'boarding_primary':    app.config.get('BOARDING_RATE_PRIMARY',    40.00),
                'boarding_additional': app.config.get('BOARDING_RATE_ADDITIONAL', 25.00),
                'daycare_multi':       app.config.get('DAYCARE_RATE_MULTI',       20.00),
                'daycare_single':      app.config.get('DAYCARE_RATE_SINGLE',      25.00),
                'addon_spa_nails':     app.config.get('ADDON_SPA_BATH_NAILS',     20.00),
                'addon_spa':           app.config.get('ADDON_SPA_BATH',           15.00),
                'addon_nails':         app.config.get('ADDON_NAIL_TRIM',          10.00),
            },
        }

    # ── Jinja filters ─────────────────────────────────────────────────────────
    app.jinja_env.filters['from_json'] = _json.loads

    def _fmt_time(t):
        if not t:
            return ''
        try:
            if isinstance(t, str):
                return _datetime.strptime(t[:5], '%H:%M').strftime('%I:%M %p').lstrip('0')
            return t.strftime('%I:%M %p').lstrip('0')
        except Exception:
            return str(t)

    app.jinja_env.filters['fmt_time'] = _fmt_time

    # ── Security headers ──────────────────────────────────────────────────────
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options']        = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
        response.headers.pop('Server', None)
        response.headers.pop('X-Powered-By', None)
        return response

    # ── Models ────────────────────────────────────────────────────────────────
    from app import models

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes import auth, customer, admin, public, kiosk
    app.register_blueprint(auth.bp)
    app.register_blueprint(customer.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(public.bp)
    app.register_blueprint(kiosk.bp)

    try:
        from app.routes import booking
        app.register_blueprint(booking.bp)
    except ImportError:
        pass

    from .reports import reports_bp
    app.register_blueprint(reports_bp)

    from app.routes.auth import index
    app.add_url_rule('/', endpoint='index', view_func=index)

    return app