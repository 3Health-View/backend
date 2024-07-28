from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from src.config.config import Config
import os

load_dotenv()

app = Flask(__name__)
bcrypt = Bcrypt(app)
cors = CORS(app)

config = Config().dev_config

if os.environ["ENVIRONMENT"] == "production":
    config = Config().production_config

app.env = config.ENV

from src.routes import api
app.register_blueprint(api, url_prefix="/api/v1")