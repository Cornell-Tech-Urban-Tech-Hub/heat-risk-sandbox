import os
import sys
sys.path.append('lambda')  # Add the lambda directory to the Python path

from lambda_function import lambda_handler

# Set up the environment variable
os.environ['BUCKET_NAME'] = 'local-test-bucket'

# Create a mock event and context
event = {}
context = None

# Run the lambda function
result = lambda_handler(event, context)

print(result)