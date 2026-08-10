from flask import Flask
from app.database import init_db


def create_app():
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    app.config.from_object("config.config.Config")

    init_db()

    from app.routes import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
