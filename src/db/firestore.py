import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('fantasyleagueoflegends-bdb374e7be01.json')
firebase_admin.initialize_app(cred)

db = firestore.client()