from flask import request, Response, json, Blueprint
import os
import pandas as pd
from src.db.firestore import db
import jwt
from src.utils import update_db, delete_email_data, fetch_data
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import zlib
import base64

data = Blueprint('data', __name__)
display_info = db.collection('display_info')
main_raw = db.collection('main_raw')
activity_raw = db.collection('activity_raw')
readiness_raw = db.collection('readiness_raw')
sleep_raw = db.collection('sleep_raw')

@data.route('/update-scores', methods = ['POST'])
def update_scores():
    try:
        full_token = request.headers.get('Authorization')
        token = full_token.split(" ")[1]
        decoded = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms='HS256')

        email = decoded.get('email')
        oura_token = decoded.get('oura_token')

        main_url = f"{os.getenv('OURA_API_BASE_URI')}/sleep" 
        sleep_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_sleep"
        activity_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_activity"
        readiness_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_readiness"

        # Get latest day in database
        try:
            current_latest = main_raw.where('email', '==', email).order_by('day', 'DESCENDING').limit(1).get()[0].to_dict()['day']
        except IndexError:
            current_latest = '1970-01-01'
        start_date = (datetime.strptime(current_latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        end_date_activity = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        params={ 
            'start_date': start_date, 
            'end_date': end_date
        }
        activity_params={
            'start_date':start_date,
            'end_date': end_date_activity
        }
        headers = { 
        'Authorization': f"Bearer {oura_token}" 
        }

        # Multithreading queries to Oura
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(fetch_data, main_url, params, headers): 'main',
                executor.submit(fetch_data, sleep_url, params, headers): 'sleep',
                executor.submit(fetch_data, activity_url, activity_params, headers): 'activity',
                executor.submit(fetch_data, readiness_url, params, headers): 'readiness'
            }
            responses = {}
            for future in as_completed(futures):
                url_type = futures[future]
                try:
                    data = future.result()
                    responses[url_type] = data
                except Exception as e:
                    return Response(
                        response=json.dumps({'message': f"Error getting {url_type} data", 'error': str(e)}),
                        status=500,
                        mimetype='application/json'
                    )

        try:
            df_main = pd.DataFrame(responses['main']['data'])
        except KeyError:
            return Response(
                response=json.dumps({'message': "Error getting data", 'error': responses['main']}),
                status=500,
                mimetype='application/json'
            )
        df_sleep = pd.DataFrame(responses['sleep']['data'])
        df_activity = pd.DataFrame(responses['activity']['data'])
        df_readiness = pd.DataFrame(responses['readiness']['data'])
        
        # Display info data
        df = df_main.merge(df_sleep[["contributors", "day", "score"]], on='day', how='left').merge(df_activity.rename({"score":"activity_score"}, axis=1)[["day","activity_score"]], on="day", how="left")
        # Cleaning
        df['contributors'] = df['contributors'].apply(lambda x: None if pd.isna(x) else x)

        # met is a dict, items a list of avg movement level every 60 secs, 1440 per day, breaks database, so we compress
        for index, row in df_activity.iterrows():
            items = row['met']['items']
            items_bytes = str(items).encode('utf-8')
            compressed = zlib.compress(items_bytes)
            compressed_base64 = base64.b64encode(compressed).decode('utf-8')
            df_activity.at[index, 'met']['items'] = compressed_base64

        # Decompression Code
        # for index, row in df_activity.iterrows():
        #     compressed_base64 = row['met']['items']
        #     compressed_bytes = base64.b64decode(compressed_base64)
        #     decompressed_bytes = zlib.decompress(compressed_bytes)
        #     decompressed_items = eval(decompressed_bytes.decode('utf-8'))
        #     df_activity.at[index, 'met']['items'] = decompressed_items

        # Display info, NoneType checks for subscripted dicts
        records = []
        for i, row in df.iterrows():
            records.append({
                "day": row["day"],
                "sleep_score": row["score"],
                "readiness_score": row.get("readiness", {}).get("score") if isinstance(row.get("readiness"), dict) else None,
                "activity_score": row["activity_score"],
                "efficiency": row["efficiency"],
                "restfulness": row.get("contributors", {}).get("restfulness") if isinstance(row.get("contributors"), dict) else None,
                "total_sleep": row["total_sleep_duration"],
                "awake": row["awake_time"],
                "rem_sleep": row["rem_sleep_duration"],
                "light_sleep": row["light_sleep_duration"],
                "deep_sleep": row["deep_sleep_duration"],
                "latency": row["latency"],
                "bedtime_start": row["bedtime_start"],
                "bedtime_end": row["bedtime_end"],
                "heart_rate": row.get("heart_rate", {}).get("items") if isinstance(row.get("heart_rate"), dict) else None,
                "average_heart_rate": row["average_heart_rate"],
                "hrv": row.get("hrv", {}).get("items") if isinstance(row.get("hrv"), dict) else None,
                "average_hrv": row["average_hrv"]
            })

        df_display = pd.DataFrame(records)
        dataframes = [df_display, df_main, df_sleep, df_activity, df_readiness]
        for dataframe in dataframes:
            dataframe['email'] = email
        update_db(df_display, display_info)
        update_db(df_main, main_raw)
        update_db(df_sleep, sleep_raw)
        update_db(df_activity, activity_raw)
        update_db(df_readiness, readiness_raw)

        return Response(
            response=json.dumps({'message': "success", 'data': records}),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        return Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )


# Significantly faster than update-scores, good for quick frontend updating
@data.route('/display-info', methods = ['GET'])
def get_display_info():
    try:
        full_token = request.headers.get('Authorization')
        token = full_token.split(" ")[1]
        decoded = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms='HS256')

        email = decoded.get('email')
        oura_token = decoded.get('oura_token')

        main_url = f"{os.getenv('OURA_API_BASE_URI')}/sleep" 
        sleep_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_sleep"
        activity_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_activity"

        # Get latest day in database
        try:
            current_latest = main_raw.where('email', '==', email).order_by('day', 'DESCENDING').limit(1).get()[0].to_dict()['day']
        except IndexError:
            current_latest = '1970-01-01'
        start_date = (datetime.strptime(current_latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        end_date_activity = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        params={ 
            'start_date': start_date, 
            'end_date': end_date
        }
        activity_params={
            'start_date':start_date,
            'end_date': end_date_activity
        }
        headers = { 
        'Authorization': f"Bearer {oura_token}" 
        }

        # Multithreading queries to Oura
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(fetch_data, main_url, params, headers): 'main',
                executor.submit(fetch_data, sleep_url, params, headers): 'sleep',
                executor.submit(fetch_data, activity_url, activity_params, headers): 'activity',
            }
            responses = {}
            for future in as_completed(futures):
                url_type = futures[future]
                try:
                    data = future.result()
                    responses[url_type] = data
                except Exception as e:
                    return Response(
                        response=json.dumps({'message': f"Error getting {url_type} data", 'error': str(e)}),
                        status=500,
                        mimetype='application/json'
                    )

        try:
            df_main = pd.DataFrame(responses['main']['data'])
        except KeyError:
            return Response(
                response=json.dumps({'message': "Error getting data", 'error': responses['main']}),
                status=500,
                mimetype='application/json'
            )
        df_sleep = pd.DataFrame(responses['sleep']['data'])
        df_activity = pd.DataFrame(responses['activity']['data'])
        
        # Display info data
        df = df_main.merge(df_sleep[["contributors", "day", "score"]], on='day', how='left').merge(df_activity.rename({"score":"activity_score"}, axis=1)[["day","activity_score"]], on="day", how="left")

        df.fillna(value=None, inplace=True)
        df.sort_values(by='day', ascending=False, inplace=True)

        # Display info, NoneType checks for subscripted dicts
        records = []
        for i, row in df.iterrows():
            records.append({
                "day": row["day"],
                "sleep_score": row["score"],
                "readiness_score": row.get("readiness", {}).get("score") if isinstance(row.get("readiness"), dict) else None,
                "activity_score": row["activity_score"],
                "efficiency": row["efficiency"],
                "restfulness": row.get("contributors", {}).get("restfulness") if isinstance(row.get("contributors"), dict) else None,
                "total_sleep": row["total_sleep_duration"],
                "awake": row["awake_time"],
                "rem_sleep": row["rem_sleep_duration"],
                "light_sleep": row["light_sleep_duration"],
                "deep_sleep": row["deep_sleep_duration"],
                "latency": row["latency"],
                "bedtime_start": row["bedtime_start"],
                "bedtime_end": row["bedtime_end"],
                "heart_rate": row.get("heart_rate", {}).get("items") if isinstance(row.get("heart_rate"), dict) else None,
                "average_heart_rate": row["average_heart_rate"],
                "hrv": row.get("hrv", {}).get("items") if isinstance(row.get("hrv"), dict) else None,
                "average_hrv": row["average_hrv"]
            })

        display_info_stream = display_info.where('email', '==', email).stream()
        for doc in display_info_stream:
            records.append(doc.to_dict())

        return Response(
            response=json.dumps({'message': "success", 'data': records}),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        return Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )

        
@data.route('/remove-data', methods = ['DELETE'])
def remove_data():
    try:
        full_token = request.headers.get('Authorization')
        token = full_token.split(" ")[1]
        decoded = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms='HS256')

        email = decoded.get('email')
        
        collections = [display_info, main_raw, activity_raw, readiness_raw, sleep_raw]

        # Multithreading deletion on all collections simultaneously
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(delete_email_data, collection, email) for collection in collections]
            for future in futures:
                future.result()
        return Response(
            response=json.dumps({'message': "success", 'data': 'Successfully deleted associated email data.'}),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        return Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )
