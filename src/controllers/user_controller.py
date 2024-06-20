from datetime import datetime, timezone
from flask import request, Response, json, Blueprint
from flask_bcrypt import Bcrypt
import jwt
import os
import time
from src.models.user_model import UserModel
from src.db.firestore import db

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