import pandas as pd
from src.db.firestore import db
import requests
import pickle

def load_label_encoder(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)

def fetch_data(url, params, headers):
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def update_db(dataframe:pd.DataFrame, collection:db.collection):
    batch = db.batch()

    for i, row in dataframe.iterrows():
        record = row.to_dict()
        doc_ref = collection.document()
        batch.set(doc_ref, record)

         # Firestore allows a maximum of 500 operations per batch
        if (i + 1) % 500 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()

def delete_email_data(collection: db.collection, email: str):
    try:
        to_remove = collection.where('email', '==', email).stream()
        batch = db.batch()
        count = 0
        for doc in to_remove:
            batch.delete(doc.reference)
            count += 1
            # Firestore allows a maximum of 500 operations per batch
            if count == 500:
                batch.commit()
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()
    except Exception as e:
        print(f"Error deleting data from {collection.id} for {email}: {e}")

default_values = {
    'int64': 0,
    'float64': 0.0,
    'bool': False,
    'object': 'Unknown'
}