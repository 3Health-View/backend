from flask import Blueprint, Response, json

hello = Blueprint('hello', __name__)

@hello.route("/", methods=["GET"])
def hello_world():
    print("Hello World!")
    return Response(
        response=json.dumps({'message': "Hello World!"}),
        status=200,
        mimetype='application/json'
    )
