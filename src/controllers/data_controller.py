from flask import request, Response, json, Blueprint
import os
from dotenv import load_dotenv
import pandas as pd
from src.db.firestore import db
from src.db.redis import setDisplayInfo, get
import jwt
from src.utils import update_db, delete_email_data, fetch_data, load_label_encoder, default_values
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import zlib
import base64
import mlflow
import pickle
import xgboost as xgb

load_dotenv()

data = Blueprint('data', __name__)
display_info = db.collection('display_info')
main_raw = db.collection('main_raw')
activity_raw = db.collection('activity_raw')
readiness_raw = db.collection('readiness_raw')
sleep_raw = db.collection('sleep_raw')
sleep_time_raw = db.collection('sleep_time_raw')


mlflow.set_tracking_uri("https://mlflow.3hv.ethanwu.net")
experiment = mlflow.get_experiment_by_name("XGBoost")
runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id], filter_string="tags.production = 'true'")
run_id = ""
for index, row in runs.iterrows():
    if row["tags.mlflow.runName"] == "Production":
        run_id = row["run_id"]

model_uri = f"runs:/{run_id}/model"
loaded_model = mlflow.pyfunc.load_model(model_uri)

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
        sleep_time_url = f"{os.getenv('OURA_API_BASE_URI')}/sleep_time"

        # Get latest day in database
        try:
            current_latest = display_info.where('email', '==', email).order_by('day', 'DESCENDING').limit(1).get()[0].to_dict()['day']
        except IndexError:
            current_latest = '1970-01-01'
        start_date = (datetime.strptime(current_latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
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
                executor.submit(fetch_data, readiness_url, params, headers): 'readiness',
                executor.submit(fetch_data, sleep_time_url, params, headers): 'sleep_time'
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
        df_sleep_time = pd.DataFrame(responses['sleep_time']['data'])
        records = []

        if len(df_main) > 0:
            # Display info data
            df = df_main.merge(df_sleep[["contributors", "day", "score"]], on='day', how='left').merge(df_activity.rename({"score":"activity_score"}, axis=1)[["day","activity_score"]], on="day", how="left")
            if(len(df_sleep_time) > 0):
                df = df.merge(df_sleep_time[["day", "recommendation", "status"]], on="day", how="left")
            # Cleaning
            df['contributors'] = df['contributors'].apply(lambda x: {} if pd.isna(x) else x)

            df.sort_values(by='day', ascending=False, inplace=True)

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
            for i, row in df.iterrows():
                records.append({
                    "day": row["day"],
                    "sleep_score": row["score"],
                    "readiness_score": row.get("readiness", {}).get("score") if isinstance(row.get("readiness"), dict) else 0,
                    "activity_score": row["activity_score"],
                    "efficiency": row["efficiency"],
                    "restfulness": row.get("contributors", {}).get("restfulness") if isinstance(row.get("contributors"), dict) else 0,
                    "total_sleep": row["total_sleep_duration"],
                    "awake": row["awake_time"],
                    "rem_sleep": row["rem_sleep_duration"],
                    "light_sleep": row["light_sleep_duration"],
                    "deep_sleep": row["deep_sleep_duration"],
                    "latency": row["latency"],
                    "bedtime_start": row["bedtime_start"],
                    "bedtime_end": row["bedtime_end"],
                    "heart_rate": row.get("heart_rate", {}).get("items") if isinstance(row.get("heart_rate"), dict) else list(),
                    "average_heart_rate": row["average_heart_rate"],
                    "hrv": row.get("hrv", {}).get("items") if isinstance(row.get("hrv"), dict) else list(),
                    "average_hrv": row["average_hrv"],
                    "type": row["type"],
                    "oura_recommendation": row.get("recommendation", ""), 
                    "oura_status": row.get("status", "")
                })

            df_display = pd.DataFrame(records)
            dataframes = [df_display, df_main, df_sleep, df_activity, df_readiness, df_sleep_time]
            for dataframe in dataframes:
                dataframe['email'] = email
            
            df_tmp = df_display.copy(deep=True)
            df_tmp['day'] = pd.to_datetime(df_tmp['day'], utc=True).dt.normalize()
            df_tmp['bedtime_start'] = pd.to_datetime(df_tmp['bedtime_start'], utc=True)
            df_tmp['bedtime_start'] = (df_tmp['bedtime_start'] - df_tmp['day']).dt.total_seconds()
            df_tmp['bedtime_end'] = pd.to_datetime(df_tmp['bedtime_end'], utc=True)
            df_tmp['bedtime_end'] = (df_tmp['bedtime_end'] - df_tmp['day']).dt.total_seconds()
            df_main_predict = df_tmp[["sleep_score", "readiness_score", "activity_score", "efficiency", "restfulness", "total_sleep", "awake", "rem_sleep", "light_sleep", "deep_sleep", "latency", "bedtime_start", "bedtime_end", "average_heart_rate", "average_hrv"]]

            artifact_path = 'label_encoder.pkl'
            local_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=artifact_path)
            label_encoder = load_label_encoder(local_path)
            recommendations = loaded_model.predict(df_main_predict)
            recommendation_original = label_encoder.inverse_transform(recommendations)

            df_display["recommendation"] = recommendation_original

            update_db(df_display, display_info)
            update_db(df_main, main_raw)
            update_db(df_sleep, sleep_raw)
            update_db(df_activity, activity_raw)
            update_db(df_readiness, readiness_raw)
            update_db(df_sleep_time, sleep_time_raw)

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

        redis_data = get(token)

        if(redis_data == None):
            print("Cache Miss")
            main_url = f"{os.getenv('OURA_API_BASE_URI')}/sleep" 
            sleep_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_sleep"
            activity_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_activity"

            # Get latest day in database
            try:
                current_latest = display_info.where('email', '==', email).order_by('day', 'DESCENDING').limit(1).get()[0].to_dict()['day']
            except IndexError:
                current_latest = '1970-01-01'
            start_date = (datetime.strptime(current_latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
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
            records = []

            if len(df_main) > 0:
                # Display info data
                df = df_main.merge(df_sleep[["contributors", "day", "score"]], on='day', how='left').merge(df_activity.rename({"score":"activity_score"}, axis=1)[["day","activity_score"]], on="day", how="left")

                df['contributors'] = df['contributors'].apply(lambda x: {} if pd.isna(x) else x)

                df.sort_values(by='day', ascending=False, inplace=True)

                # Display info, NoneType checks for subscripted dicts
                for i, row in df.iterrows():
                    records.append({
                        "day": row["day"],
                        "sleep_score": row["score"],
                        "readiness_score": row.get("readiness", {}).get("score") if isinstance(row.get("readiness"), dict) else 0,
                        "activity_score": row["activity_score"],
                        "efficiency": row["efficiency"],
                        "restfulness": row.get("contributors", {}).get("restfulness") if isinstance(row.get("contributors"), dict) else 0,
                        "total_sleep": row["total_sleep_duration"],
                        "awake": row["awake_time"],
                        "rem_sleep": row["rem_sleep_duration"],
                        "light_sleep": row["light_sleep_duration"],
                        "deep_sleep": row["deep_sleep_duration"],
                        "latency": row["latency"],
                        "bedtime_start": row["bedtime_start"],
                        "bedtime_end": row["bedtime_end"],
                        "heart_rate": row.get("heart_rate", {}).get("items") if isinstance(row.get("heart_rate"), dict) else list(),
                        "average_heart_rate": row["average_heart_rate"],
                        "hrv": row.get("hrv", {}).get("items") if isinstance(row.get("hrv"), dict) else list(),
                        "average_hrv": row["average_hrv"],
                        "type": row["type"],
                        "oura_recommendation": row.get("recommendation", ""), 
                        "oura_status": row.get("status", ""),
                    })
            
            df_display = pd.DataFrame(records)
            df_tmp = df_display.copy(deep=True)
            df_tmp['day'] = pd.to_datetime(df_tmp['day'], utc=True).dt.normalize()
            df_tmp['bedtime_start'] = pd.to_datetime(df_tmp['bedtime_start'], utc=True)
            df_tmp['bedtime_start'] = (df_tmp['bedtime_start'] - df_tmp['day']).dt.total_seconds()
            df_tmp['bedtime_end'] = pd.to_datetime(df_tmp['bedtime_end'], utc=True)
            df_tmp['bedtime_end'] = (df_tmp['bedtime_end'] - df_tmp['day']).dt.total_seconds()
            df_main_predict = df_tmp[["sleep_score", "readiness_score", "activity_score", "efficiency", "restfulness", "total_sleep", "awake", "rem_sleep", "light_sleep", "deep_sleep", "latency", "bedtime_start", "bedtime_end", "average_heart_rate", "average_hrv"]]

            artifact_path = 'label_encoder.pkl'
            local_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=artifact_path)
            label_encoder = load_label_encoder(local_path)
            recommendations = loaded_model.predict(df_main_predict)
            recommendation_original = label_encoder.inverse_transform(recommendations)

            df_display["recommendation"] = recommendation_original

            for column in df_display.columns:
                dtype = df_display[column].dtype
                if dtype == 'object' and pd.api.types.is_categorical_dtype(df_display[column]):
                    df_display[column].fillna(default_values['object'], inplace=True)
                    df_display[column] = df_display[column].astype('category')
                elif dtype == 'object':
                    df_display[column].fillna(default_values['object'], inplace=True)
                else:
                    df_display[column].fillna(default_values[str(dtype)], inplace=True)
                    df_display[column] = df_display[column].astype(dtype)

            records = df_display.to_dict(orient='records')

            display_info_stream = display_info.where('email', '==', email).stream()
            for doc in display_info_stream:
                records.append(doc.to_dict())

            records.sort(key=lambda x: x['day'], reverse=True)
            setDisplayInfo(token, records)

            return Response(
                response=json.dumps({'message': "success", 'data': records}),
                status=200,
                mimetype='application/json'
            )
        else:
            print("Cache Hit")
            return Response(
                response=json.dumps({'message': "success", 'data': redis_data}),
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
        
        collections = [display_info, main_raw, activity_raw, readiness_raw, sleep_raw, sleep_time_raw]

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
