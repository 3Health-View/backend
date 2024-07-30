from dotenv import load_dotenv
import os
import redis
from redis.commands.json.path import Path

load_dotenv()

redis_db = redis.Redis(
  host=os.getenv("REDIS_HOST"),
  port=os.getenv("REDIS_PORT"),
  password=os.getenv("REDIS_PWD"))


def setDisplayInfo(key, data):
    redis_db.json().set(key, Path.root_path(), data)
    redis_db.expire(key, 60)

def get(key):
    data = redis_db.json().get(key)
    return data