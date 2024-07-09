from flask import request, Response, json, Blueprint
import os
import requests
import pandas as pd
from src.db.firestore import db
import jwt
from src.utils import update_db
from datetime import datetime, timedelta

data = Blueprint('data', __name__)
display_info = db.collection('display_info')
main_raw = db.collection('main_raw')
activity_raw = db.collection('activity_raw')
readiness_raw = db.collection('readiness_raw')
sleep_raw = db.collection('sleep_raw')

@data.route('/scores', methods = ['POST'])
def getScores():
    try:

        data = request.json
        full_token = request.headers.get('Authorization')
        token = full_token.split(" ")[1]
        decoded = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms='HS256')

        email = decoded.get('email')

        required_fields = ['ouraToken', 'startDate', 'endDate']
        if all(field in data for field in required_fields):
            main_url = f"{os.getenv('OURA_API_BASE_URI')}/sleep" 
            sleep_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_sleep"
            activity_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_activity"
            readiness_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_readiness"

            params={ 
                'start_date': data['startDate'], 
                'end_date': data['endDate'] 
            }
            activity_params={
                'start_date':data['startDate'],
                'end_date': (datetime.strptime(data['endDate'], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            }
            headers = { 
            'Authorization': f"Bearer {data['ouraToken']}" 
            }

            main_response = requests.get(main_url, headers=headers, params=params)
            sleep_response = requests.get(sleep_url, headers=headers, params=params)
            activity_response = requests.get(activity_url, headers=headers, params=activity_params)
            readiness_response = requests.get(readiness_url, headers=headers, params=params)

            try:
                df_main = pd.DataFrame(main_response.json()['data'])
            except KeyError:
                return Response(
                    response=main_response.json()['detail'],
                    status=main_response.status_code,
                    mimetype='application/json'
                )
            df_sleep = pd.DataFrame(sleep_response.json()['data'])
            df_activity = pd.DataFrame(activity_response.json()['data'])
            df_readiness = pd.DataFrame(readiness_response.json()['data'])
            
            df = df_main.merge(df_sleep[["contributors", "day", "score"]], on='day', how='left').merge(df_activity.rename({"score":"activity_score"}, axis=1)[["day","activity_score"]], on="day", how="left")

            records = []
            for i, row in df.iterrows():
                records.append({
                    "email":email,
                    "day": row["day"],
                    "sleep_score": row["score"],
                    "readiness_score": row["readiness"]["score"],
                    "activity_score": row["activity_score"],
                    "efficiency": row["efficiency"],
                    "restfulness": row["contributors"]["restfulness"],
                    "total_sleep": row["total_sleep_duration"],
                    "awake": row["awake_time"],
                    "rem_sleep": row["rem_sleep_duration"],
                    "light_sleep": row["light_sleep_duration"],
                    "deep_sleep": row["deep_sleep_duration"],
                    "latency": row["latency"],
                    "bedtime_start": row["bedtime_start"],
                    "bedtime_end": row["bedtime_end"],
                    "heart_rate": row["heart_rate"]["items"],
                    "average_heart_rate": row["average_heart_rate"],
                    "hrv": row["hrv"]["items"],
                    "average_hrv": row["average_hrv"]
                })

            df_display = pd.DataFrame(records)
            # update_db(df_display, display_info, {})
            # update_db(df_main, main_raw, {'email':email})
            # update_db(df_sleep, sleep_raw, {'email':email})
            # update_db(df_activity, activity_raw, {'email':email})
            # update_db(df_readiness, readiness_raw, {'email':email})

            return Response(
                response=json.dumps({'message': "success", 'data': records}),
                status=200,
                mimetype='application/json'
            )

        else:
            return Response(
                response=json.dumps({'message': "[ouraToken, startDate, endDate] is required!"}),
                status=400,
                mimetype='application/json'
            )
    except Exception as e:
        return Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )
