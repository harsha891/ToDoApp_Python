import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import boto3
import jwt
from jwt import PyJWKClient

load_dotenv()

app = Flask(__name__)
app.url_map.strict_slashes = False
CORS(app)

COGNITO_POOL_ID = os.getenv("COGNITO_POOL_ID")
COGNITO_REGION = os.getenv("COGNITO_REGION")
APP_CLIENT_ID = os.getenv("YOUR_APP_CLIENT_ID")  
AWS_REGION = os.getenv('AWS_REGION')
DB_TABLE = os.getenv('DB_TABLE')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DB_TABLE)

sns = boto3.client('sns', region_name=AWS_REGION)

jwks_url = "https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_GY5F1u4OW/.well-known/jwks.json"

def verify_token(token):
    try:
        # Initialize the PyJWKClient with your JWKS URL
        jwk_client = PyJWKClient(jwks_url)
        
        # Fetching the signing key
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        
        decoded_token = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APP_CLIENT_ID,
            issuer=f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_POOL_ID}"
        )
        
        return decoded_token

    except Exception as e:
        # Log the error for debugging purposes
        print("Token verification failed:", e)
        return False

@app.route('/')
@app.route('/tasks', methods=['GET'])
def get_tasks():
    response = table.scan()
    tasks = response.get('Items', [])
    return jsonify(tasks), 200

@app.route('/tasks', methods=['POST'])
def create_task():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not verify_token(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    task = {
        'id': str(uuid.uuid4()),
        'description': data.get('description', ''),
        'dueDate': data.get('dueDate', None),
        'priority': data.get('priority', None),
        'category': data.get('category', None),
        'completed': False,
    }
    table.put_item(Item=task)

    message = f"A new task has been created: {task['description']}"
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=message,
        Subject='New Task Notification',
        MessageGroupId='default'
    )
    
    return jsonify(task), 201

@app.route('/tasks/<string:task_id>', methods=['PUT'])
def update_task(task_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not verify_token(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    
    # Build a dynamic update expression
    update_clauses = []
    expression_attribute_values = {}

    # Update description if provided
    if 'description' in data:
        update_clauses.append("description = :d")
        expression_attribute_values[":d"] = data['description']

    # Update completed status if provided
    if 'completed' in data:
        update_clauses.append("completed = :c")
        expression_attribute_values[":c"] = data['completed']

    # Update dueDate if provided
    if 'dueDate' in data:
        update_clauses.append("dueDate = :dd")
        expression_attribute_values[":dd"] = data['dueDate']

    # Update priority if provided
    if 'priority' in data:
        update_clauses.append("priority = :p")
        expression_attribute_values[":p"] = data['priority']

    # Update category if provided
    if 'category' in data:
        update_clauses.append("category = :cat")
        expression_attribute_values[":cat"] = data['category']

    # If no fields are provided, return an error
    if not update_clauses:
        return jsonify({'message': 'No update parameters provided'}), 400

    update_expression = "set " + ", ".join(update_clauses)

    table.update_item(
        Key={'id': task_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values
    )
    return jsonify({'message': 'Task updated successfully'}), 200

@app.route('/tasks/<string:task_id>', methods=['DELETE'])
def delete_task(task_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not verify_token(token):
        return jsonify({'error': 'Unauthorized'}), 401

    table.delete_item(Key={'id': task_id})
    return jsonify({'message': 'Task deleted successfully'}), 200

if __name__ == '__main__':
    app.run(debug=True)