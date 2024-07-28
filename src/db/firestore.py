from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
import os

load_dotenv()

cred = credentials.Certificate(os.getenv("GCP_SA_CRED_PATH"))
firebase_admin.initialize_app(cred)

db = firestore.client()