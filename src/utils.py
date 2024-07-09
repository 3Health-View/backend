import pandas as pd
from src.db.firestore import db

def update_db(dataframe:pd.DataFrame, collection:db.collection, to_add:dict()):
     for i, row in dataframe.iterrows():
        record = row.to_dict()
        record.update(to_add)
        day_check = collection.where('day', '==', row['day']).get()
        if day_check:
            for doc in day_check:
                doc.reference.delete()
        collection.add(record)