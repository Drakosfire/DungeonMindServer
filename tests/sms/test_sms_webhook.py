import os
from twilio.request_validator import RequestValidator
import requests
from dotenv import load_dotenv
import logging
from twilio.rest import Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv('.env.development')

# Get Twilio credentials from environment
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
account_sid = os.environ.get('TWILIO_ACCOUNT_SID')  # We'll need this for the API test
validator = RequestValidator(auth_token)

# First, let's verify the auth token works by making a real Twilio API call
def test_twilio_credentials():
    logger.info("\nTesting Twilio credentials...")
    try:
        client = Client(account_sid, auth_token)
        # Try to fetch account info - this will fail if credentials are invalid
        account = client.api.accounts(account_sid).fetch()
        logger.info(f"✅ Twilio credentials are valid! Account status: {account.status}")
        return True
    except Exception as e:
        logger.error(f"❌ Twilio credentials are invalid: {str(e)}")
        return False

# Our local endpoint
url = 'http://localhost:7860/api/sms/receive'

# Test parameters that match what Twilio would send
params = {
    'Body': 'Hello World',
    'From': '+1234567890',
    'MessageSid': 'SM123456789',
    'To': '+18005551212'
}

def test_url(method, url, params, valid):
    if method == "GET":
        url = url + '?' + '&'.join(f"{k}={v}" for k, v in params.items())
        params = {}

    # Debug signature computation
    logger.info(f"\nSignature computation details:")
    logger.info(f"Auth Token: {'*' * len(auth_token) if auth_token else 'None'}")
    logger.info(f"URL for signature: {url}")
    logger.info(f"Params for signature: {params}")

    # Compute signature
    if valid:
        signature = validator.compute_signature(url, params)
    else:
        signature = validator.compute_signature("http://invalid.com", params)

    headers = {
        'X-Twilio-Signature': signature,
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    logger.info(f"\nTesting {method} request:")
    logger.info(f"URL: {url}")
    logger.info(f"Headers: {headers}")
    logger.info(f"Params: {params}")
    logger.info(f"EXTERNAL_SMS_ENDPOINT: {os.getenv('EXTERNAL_SMS_ENDPOINT')}")

    response = requests.request(method, url, headers=headers, data=params)
    logger.info(f'HTTP {method} with {"valid" if valid else "invalid"} signature returned {response.status_code}')
    logger.info(f'Response: {response.text}\n')

# First test the credentials
if test_twilio_credentials():
    # Only run the webhook tests if credentials are valid
    logger.info("Starting webhook signature tests...")
    test_url('POST', url, params, True)
    test_url('POST', url, params, False)
else:
    logger.error("Skipping webhook tests due to invalid credentials") 