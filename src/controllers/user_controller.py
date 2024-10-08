from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import request, Response, json, Blueprint
from flask_bcrypt import Bcrypt
import jwt
import os
import requests
from requests.auth import HTTPBasicAuth
import time
from src.models.user_model import UserModel
from src.db.firestore import db

load_dotenv()

bcrypt = Bcrypt()
users = Blueprint('users', __name__)
users_ref = db.collection('users')

@users.route("/login", methods = ["POST"])
def handle_login():
    try:
        data = request.json
        required_fields = ['email', 'password']
        if all(field in data for field in required_fields):
            user = users_ref.where('email', '==', data['email']).limit(1).get()
            if user:
                user_obj = user[0].to_dict()
                if bcrypt.check_password_hash(user_obj.get('password'), data['password']):
                    payload = {
                        'iat': datetime.now(timezone.utc),
                        'exp': time.time() + 86400,
                        'email': user_obj.get('email'),
                        'firstName': user_obj.get('firstName'),
                        'lastName': user_obj.get('lastName'),
                        'oura_token': user_obj.get('ouraToken'),
                        'oura_refresh': user_obj.get('ouraRefresh')
                    }

                    token = jwt.encode(payload, os.getenv('SECRET_KEY'), algorithm='HS256')

                    return Response(
                        response=json.dumps({'message': "User Sign In Successful", 'token': token}),
                        status=200,
                        mimetype='application/json'
                    )
                else:
                    return Response(
                        response=json.dumps({'message': "Incorrect Password"}),
                        status=401,
                        mimetype='application/json'
                    )
            else:
                return Response(
                    response=json.dumps({'message': "User does not exist"}),
                    status=404,
                    mimetype='application/json'
                )
        else:
            return Response(
                response=json.dumps({'message': "[email, password] is required!"}),
                status=400,
                mimetype='application/json'
            )
    except Exception as e:
        return Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )

@users.route('/signup', methods = ["POST"])
def handle_signup():
    try:
        data = request.json
        required_fields = ['email', 'firstName', 'lastName', 'password']
        if all(field in data for field in required_fields):
            user = users_ref.where('email', '==', data['email']).limit(1).get()
            if not user:
                user_obj = UserModel(email=data['email'],
                                     first_name=data['firstName'],
                                     last_name=data['lastName'],
                                     password=bcrypt.generate_password_hash(data['password']).decode('utf-8'))
                
                users_ref.add(user_obj.to_dict())

                payload = {
                    'iat': datetime.now(timezone.utc),
                    'exp': time.time() + 86400,
                    'email': user_obj.email,
                    'firstName': user_obj.first_name,
                    'lastName': user_obj.last_name,
                    'oura_token': user_obj.oura_token,
                    'oura_refresh': user_obj.oura_refresh
                }
                
                token = jwt.encode(payload, os.getenv('SECRET_KEY'), algorithm='HS256')

                return Response(
                    response=json.dumps({'message': "User Sign Up Successful", 'token': token}),
                    status=201,
                    mimetype='application/json'
                )
            else:
                return Response(
                    response=json.dumps({'message': "User already exists."}),
                    status=409,
                    mimetype='application/json'
                )
        else:
            return Response(
                response=json.dumps({'message': "[email, firstName, lastName, username, password] are required!"}),
                status=400,
                mimetype='application/json'
            )
    except Exception as e:
        return  Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )

@users.route('/update-oura', methods = ["PATCH"])
def update_oura():
    try:
        data = request.json

        full_token = request.headers.get('Authorization')
        token = full_token.split(" ")[1]
        decoded = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms='HS256')

        if(time.time() > decoded.get('exp')):
            return Response(
                response=json.dumps({'message': "Token has expired"}),
                status=401,
                mimetype='application/json'
            )
        
        required_fields = ['ouraToken', 'ouraRefresh']
        if all(field in data for field in required_fields):
            user = users_ref.where('email', '==', decoded.get("email")).limit(1).get()

            if user:
                user_doc_ref = users_ref.document(user[0].id)
                user_doc_ref.update({'ouraToken': data['ouraToken'], 'ouraRefresh': data['ouraRefresh']})
                new_user_obj = user_doc_ref.get().to_dict()

                payload = {
                    'iat': datetime.now(timezone.utc),
                    'exp': time.time() + 86400,
                    'email': new_user_obj.get('email'),
                    'firstName': new_user_obj.get('firstName'),
                    'lastName': new_user_obj.get('lastName'),
                    'oura_token': new_user_obj.get('ouraToken'),
                    'oura_refresh': new_user_obj.get('ouraRefresh')
                }

                token = jwt.encode(payload, os.getenv('SECRET_KEY'), algorithm='HS256')

                return Response(
                    response=json.dumps({'message': "User Oura Tokens Updated", 'token': token}),
                    status=200,
                    mimetype='application/json'
                )
            else:
                return Response(
                    response=json.dumps({'message': "User does not exist"}),
                    status=404,
                    mimetype='application/json'
                )
        else:
            return Response(
                response=json.dumps({'message': "[ouraToken, ouraRefresh] is required!"}),
                status=400,
                mimetype='application/json'
            )
        
    except Exception as e:
        return Response(
            response= json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )


@users.route('/get-token', methods = ["POST"])
def get_token():
    try:
        data = request.json
        required_fields = ['code', 'redirectUrl']
        if all(field in data for field in required_fields):
            url = f"https://api.ouraring.com/oauth/token?grant_type=authorization_code&code={data['code']}&redirect_uri={data['redirectUrl']}"
            resp = requests.post(url, auth=HTTPBasicAuth(os.getenv('CLIENT_ID'), os.getenv('CLIENT_SECRET')))
            return Response(
                response=json.dumps(resp.json()),
                status=resp.status_code,
                mimetype='application/json'
            )
        else:
            return Response(
                response=json.dumps({'message': "[code, redirectUrl] is required!"}),
                status=400,
                mimetype='application/json'
            )
    except Exception as e:
        return Response(
            response=json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )
    
@users.route('/refresh-token', methods = ["POST"])
def refresh_token():
    try:
        data = request.json
        required_fields = ['refreshToken']
        if all(field in data for field in required_fields):
            url = f"https://api.ouraring.com/oauth/token?grant_type=refresh_token&refresh_token={data['refreshToken']}"
            resp = requests.post(url, auth=HTTPBasicAuth(os.getenv('CLIENT_ID'), os.getenv('CLIENT_SECRET')))
            return Response(
                response=json.dumps(resp.json()),
                status=resp.status_code,
                mimetype='application/json'
            )
        else:
            return Response(
                response=json.dumps({'message': "[code, redirectUrl] is required!"}),
                status=400,
                mimetype='application/json'
            )
    except Exception as e:
        return Response(
            response=json.dumps({'message': "Error has occurred", 'error': str(e)}),
            status=500,
            mimetype='application/json'
        )