from twilio.request_validator import RequestValidator
import os
from dotenv import load_dotenv
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = '../../.env.development'
if not os.path.exists(env_path):
    logger.error(f"Error: {env_path} not found!")
    logger.error(f"Current working directory: {os.getcwd()}")
    sys.exit(1)

load_dotenv(env_path)

# Get Twilio credentials and configuration from environment
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
webhook_url = os.environ.get('TWILIO_WEBHOOK_URL', 'https://www.dungeonmind.net/api/sms/receive')

if not auth_token:
    logger.error("Error: TWILIO_AUTH_TOKEN not found in environment variables!")
    logger.error("Available environment variables:")
    for key in os.environ:
        if 'TWILIO' in key:
            logger.error(f"{key}: {'*' * len(os.environ[key]) if os.environ[key] else 'Not set'}")
    sys.exit(1)

if not account_sid:
    logger.error("Error: TWILIO_ACCOUNT_SID not found in environment variables!")
    sys.exit(1)

logger.info(f"Successfully loaded Twilio credentials")
validator = RequestValidator(auth_token)

# Test parameters - using environment variables where possible
params = {
    'MessageSid': os.environ.get('TEST_MESSAGE_SID', 'SM12345678901234567890123456789012'),
    'AccountSid': account_sid,
    'From': os.environ.get('TEST_FROM_NUMBER', ' 14017122661'),
    'To': os.environ.get('TEST_TO_NUMBER', ' 15558675310'),
    'Body': os.environ.get('TEST_MESSAGE_BODY', 'Hello from Twilio test'),
    'NumMedia': '0',
    'NumSegments': '1'
}

# Compute signature
signature = validator.compute_signature(webhook_url, params)

# Generate curl command
curl_cmd = f"""curl -X POST {webhook_url} \\
  -H "Content-Type: application/x-www-form-urlencoded" \\
  -H "x-twilio-signature: {signature}" \\
  -d "MessageSid={params['MessageSid']}&AccountSid={params['AccountSid']}&From={params['From']}&To={params['To']}&Body={params['Body']}&NumMedia=0&NumSegments=1"
"""

logger.info("\nGenerated curl command:")
logger.info(curl_cmd)