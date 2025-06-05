from twilio.request_validator import RequestValidator
import os
from dotenv import load_dotenv
import sys

# Load environment variables
env_path = '../../.env.development'
if not os.path.exists(env_path):
    print(f"Error: {env_path} not found!")
    print(f"Current working directory: {os.getcwd()}")
    sys.exit(1)

load_dotenv(env_path)

# Get Twilio credentials
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
if not auth_token:
    print("Error: TWILIO_AUTH_TOKEN not found in environment variables!")
    print("Available environment variables:")
    for key in os.environ:
        if 'TWILIO' in key:
            print(f"{key}: {'*' * len(os.environ[key]) if os.environ[key] else 'Not set'}")
    sys.exit(1)

print(f"Successfully loaded TWILIO_AUTH_TOKEN: {'*' * len(auth_token)}")
validator = RequestValidator(auth_token)

# Test parameters - matching exactly what the server receives
url = 'http://www.dungeonmind.net/api/sms/receive'
params = {
    'MessageSid': 'SM12345678901234567890123456789012',
    'AccountSid': 'AC14b4f3b47bc469e92852e3971c33851c',
    'From': ' 14017122661',
    'To': ' 15558675310',
    'Body': 'Hello from Twilio test',
    'NumMedia': '0',
    'NumSegments': '1'
}

# Compute signature
signature = validator.compute_signature(url, params)

# Generate curl command
curl_cmd = f"""curl -X POST {url} \\
  -H "Content-Type: application/x-www-form-urlencoded" \\
  -H "x-twilio-signature: {signature}" \\
  -d "MessageSid=SM12345678901234567890123456789012&AccountSid=AC14b4f3b47bc469e92852e3971c33851c&From= 14017122661&To= 15558675310&Body=Hello from Twilio test&NumMedia=0&NumSegments=1"
"""

print("\nGenerated curl command:")
print(curl_cmd) 