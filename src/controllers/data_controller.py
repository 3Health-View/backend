from flask import request, Response, json, Blueprint
import os
import requests


data = Blueprint('data', __name__)

@data.route('/scores', methods = ['POST'])
def getScores():
    try:

        data = request.json

        required_fields = ['ouraToken', 'startDate', 'endDate']
        if all(field in data for field in required_fields):
            sleep_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_sleep"
            activity_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_activity"
            readiness_url = f"{os.getenv('OURA_API_BASE_URI')}/daily_readiness"

            params={ 
                'start_date': data['startDate'], 
                'end_date': data['endDate'] 
            }
            headers = { 
            'Authorization': f"Bearer {data['ouraToken']}" 
            }

            sleep_response = requests.get(sleep_url, headers=headers, params=params)
            activity_response = requests.get(activity_url, headers=headers, params=params)
            readiness_response = requests.get(readiness_url, headers=headers, params=params)

            sleep_score = sleep_response.json().get("data")[0].get("score")
            activity_score = activity_response.json().get("data")[0].get("score")
            readiness_score = readiness_response.json().get("data")[0].get("score")

            return Response(
                response=json.dumps({'message': "success", 'data': {'sleep': sleep_score, 'activity': activity_score, 'readiness': readiness_score}}),
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