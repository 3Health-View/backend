from flask import Blueprint
from src.controllers.data_controller import data
from src.controllers.hello import hello
from src.controllers.user_controller import users

api = Blueprint('api', __name__)

api.register_blueprint(data, url_prefix="/data")

api.register_blueprint(hello, url_prefix="/hello")

api.register_blueprint(users, url_prefix="/users")