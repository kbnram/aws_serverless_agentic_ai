"""
AWS Service Abstraction Layer - minimalist patterns for AWS services
"""
from core_dependencies import aws, ENV, DEBUG
import json
import time
from functools import wraps

# Service clients with single-instance caching
_clients = {}

def get_client(service_name, **kwargs):
    """Get cached boto3 client"""
    if service_name not in _clients:
        _clients[service_name] = aws()["boto3"].client(service_name, **kwargs)
    return _clients[service_name]

# DynamoDB Patterns
class DynamoDB:
    @staticmethod
    def put(table_name, item):
        """Put item into DynamoDB table"""
        return get_client('dynamodb').put_item(
            TableName=table_name,
            Item=aws()["boto3"].dynamodb.types.TypeSerializer().serialize(item)['M']
        )
    
    @staticmethod
    def get(table_name, key):
        """Get item from DynamoDB table"""
        response = get_client('dynamodb').get_item(
            TableName=table_name,
            Key={k: aws()["boto3"].dynamodb.types.TypeSerializer().serialize(v) for k, v in key.items()}
        )
        if 'Item' not in response:
            return None
        return aws()["boto3"].dynamodb.types.TypeDeserializer().deserialize({'M': response['Item']})
    
    @staticmethod
    def query(table_name, key_condition, index_name=None):
        """Query DynamoDB table"""
        params = {
            'TableName': table_name,
            'KeyConditionExpression': key_condition
        }
        if index_name:
            params['IndexName'] = index_name
        
        response = get_client('dynamodb').query(**params)
        return [
            aws()["boto3"].dynamodb.types.TypeDeserializer().deserialize({'M': item})
            for item in response.get('Items', [])
        ]

# S3 Patterns
class S3:
    @staticmethod
    def put_object(bucket, key, body, content_type='application/json'):
        """Store object in S3"""
        return get_client('s3').put_object(
            Bucket=bucket,
            Key=key,
            Body=body if not isinstance(body, dict) else json.dumps(body),
            ContentType=content_type
        )
    
    @staticmethod
    def get_object(bucket, key):
        """Get object from S3"""
        try:
            response = get_client('s3').get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            if response.get('ContentType') == 'application/json':
                return json.loads(content)
            return content
        except aws()["exceptions"]["ClientError"] as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise

# SQS Patterns
class SQS:
    @staticmethod
    def send_message(queue_url, message_body, delay_seconds=0):
        """Send message to SQS queue"""
        return get_client('sqs').send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body) if isinstance(message_body, dict) else message_body,
            DelaySeconds=delay_seconds
        )
    
    @staticmethod
    def receive_messages(queue_url, max_messages=1, wait_time=5):
        """Receive messages from SQS queue"""
        response = get_client('sqs').receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time
        )
        
        messages = []
        for msg in response.get('Messages', []):
            try:
                body = json.loads(msg['Body'])
            except:
                body = msg['Body']
                
            messages.append({
                'id': msg['MessageId'],
                'receipt_handle': msg['ReceiptHandle'],
                'body': body
            })
        return messages
    
    @staticmethod
    def delete_message(queue_url, receipt_handle):
        """Delete message from SQS queue"""
        return get_client('sqs').delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle
        )

# Lambda Patterns
class Lambda:
    @staticmethod
    def invoke(function_name, payload, invocation_type='RequestResponse'):
        """Invoke Lambda function"""
        response = get_client('lambda').invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=json.dumps(payload) if isinstance(payload, dict) else payload
        )
        
        if invocation_type == 'RequestResponse':
            return json.loads(response['Payload'].read())
        return response

# Secret Manager Patterns
class Secrets:
    @staticmethod
    def get_secret(secret_id):
        """Get secret from Secrets Manager"""
        response = get_client('secretsmanager').get_secret_value(SecretId=secret_id)
        return json.loads(response['SecretString'])

# Serverless-oriented retry decorator
def retry(max_attempts=3, base_delay=0.1, exponential=True):
    """Retry decorator optimized for Lambda execution"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = base_delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        if exponential:
                            time.sleep(delay)
                            delay *= 2
                        else:
                            time.sleep(base_delay)
            
            raise last_exception
        return wrapper
    return decorator
