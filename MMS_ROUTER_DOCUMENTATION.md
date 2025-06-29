# MMS Router Documentation

## Overview

The SMS router has been updated to handle MMS (Multimedia Messaging Service) messages in addition to regular SMS messages. This allows the system to receive and process images, videos, audio files, and other media attachments sent via text message.

## New Features

### 1. MMS Message Processing
- **Automatic detection** of MMS vs SMS messages using multiple indicators
- **Media extraction** from Twilio webhook data
- **Media type validation** with support for common formats
- **Enhanced logging** with comprehensive media and message information
- **Twilio API compliance** following official Message Resource structure

### 2. Enhanced Validation
- **Message SID validation** (SMS starts with "SM", MMS starts with "MM")
- **Webhook format validation** ensuring required Twilio fields are present
- **Consistency checking** between NumMedia and MessageSid type
- **Comprehensive error handling** with detailed validation messages

### 3. Supported Media Types

The router supports the following media types:

#### Images
- `image/jpeg`, `image/jpg`
- `image/png`
- `image/gif`
- `image/webp`

#### Videos
- `video/mp4`
- `video/quicktime`
- `video/mpeg`
- `video/webm`

#### Audio
- `audio/mpeg`, `audio/mp3`
- `audio/wav`
- `audio/ogg`
- `audio/webm`

#### Documents
- `application/pdf`
- `text/plain`
- `text/vcard`

### 4. New API Endpoints

#### GET `/api/sms/supported-media-types`
Returns the list of supported media types.

**Response:**
```json
{
  "supported_types": ["image/jpeg", "image/png", ...],
  "count": 13
}
```

#### GET `/api/sms/download-media?media_url=<twilio_url>`
Downloads media from a Twilio URL (for testing/debugging).

**Response:**
```json
{
  "success": true,
  "size_bytes": 12345,
  "message": "Media downloaded successfully"
}
```

## Message Payload Structure

### SMS Message (NumMedia = 0)
```json
{
  "from": "+1234567890",
  "to": "+1987654321",
  "body": "Hello world",
  "message_sid": "SM123...",
  "account_sid": "AC123...",
  "api_version": "2010-04-01",
  "status": "received",
  "direction": "inbound",
  "timestamp": "2023-12-01T10:00:00Z",
  "message_type": "SMS",
  "num_media": 0,
  "media": [],
  "conversationId": "",
  "metadata": {
    "phoneNumber": "+1234567890",
    "messageType": "SMS",
    "mediaCount": 0,
    "supportedMediaCount": 0,
    "unsupportedMediaCount": 0,
    "twilioAccountSid": "AC123...",
    "twilioApiVersion": "2010-04-01",
    "messageStatus": "received"
  },
  "subresource_info": {
    "media_available": false,
    "media_urls_expire": true,
    "note": "Media URLs expire after a few hours. Download immediately if needed."
  }
}
```

### MMS Message (NumMedia > 0)
```json
{
  "from": "+1234567890",
  "to": "+1987654321",
  "body": "Check out this image!",
  "message_sid": "MM123...",
  "account_sid": "AC123...",
  "api_version": "2010-04-01",
  "status": "received",
  "direction": "inbound",
  "timestamp": "2023-12-01T10:00:00Z",
  "message_type": "MMS",
  "num_media": 2,
  "media": [
    {
      "url": "https://api.twilio.com/2010-04-01/Accounts/.../Media/ME123",
      "content_type": "image/jpeg",
      "index": 0,
      "supported": true
    },
    {
      "url": "https://api.twilio.com/2010-04-01/Accounts/.../Media/ME124",
      "content_type": "application/octet-stream",
      "index": 1,
      "supported": false
    }
  ],
  "conversationId": "",
  "metadata": {
    "phoneNumber": "+1234567890",
    "messageType": "MMS",
    "mediaCount": 2,
    "supportedMediaCount": 1,
    "unsupportedMediaCount": 1,
    "twilioAccountSid": "AC123...",
    "twilioApiVersion": "2010-04-01",
    "messageStatus": "received"
  },
  "subresource_info": {
    "media_available": true,
    "media_urls_expire": true,
    "note": "Media URLs expire after a few hours. Download immediately if needed."
  }
}
```

## Implementation Details

### Media Processing Flow

1. **Webhook Reception**: Twilio sends POST to `/api/sms/receive`
2. **Format Validation**: Validate webhook follows Twilio Message Resource format
3. **Data Extraction**: Extract all standard Twilio fields and media data
4. **Message Type Detection**: Determine SMS/MMS using NumMedia and MessageSid pattern
5. **Media Validation**: Check each media type against supported list
6. **Classification**: Mark each media item as supported/unsupported
7. **Payload Construction**: Build Twilio-compliant payload with enhanced data
8. **Forwarding**: Send to external API with comprehensive message information

### Enhanced Validation

The router now performs comprehensive validation of incoming webhooks:

#### Required Field Validation
- Ensures `From` and `MessageSid` fields are present
- Returns HTTP 400 for missing required fields

#### Message SID Format Validation
- **SMS messages**: MessageSid must start with "SM"
- **MMS messages**: MessageSid must start with "MM"
- Logs warnings for unexpected SID formats

#### Consistency Checking
- Validates NumMedia matches MessageSid type expectation
- Warns about inconsistencies (e.g., MM SID with NumMedia=0)
- Provides detailed logging for troubleshooting

#### Media Data Validation
- Validates NumMedia is a valid positive integer
- Checks for negative or invalid NumMedia values
- Ensures MediaUrl and MediaContentType pairs are complete

### Logging Enhancements

The router now provides comprehensive logging following Twilio's Message Resource structure:

```
=== Incoming SMS/MMS Webhook Request ===
Request URL: https://dungeonmind.net/api/sms/receive
Request method: POST
...

=== Message Details ===
MessageSid: MM123... (Type: MMS)
From: +1234567890
To: +1987654321
AccountSid: AC123...
Status: received
ApiVersion: 2010-04-01
Body: Check out this image!
NumMedia: 2
Supported media items: 1
Unsupported media items: 1
Media 0 ✓: image/jpeg - https://api.twilio.com/...
Media 1 ✗: application/octet-stream - https://api.twilio.com/...

=== Forwarding Message ===
Message Type: MMS
Total Media Items: 2 (Supported: 1, Unsupported: 1)
  ✓ image/jpeg: https://api.twilio.com/...
  ✗ application/octet-stream: https://api.twilio.com/...
```

### Security Considerations

1. **Media URL Expiration**: Twilio media URLs expire after a few hours
2. **Authentication**: Media downloads require Twilio credentials
3. **Validation**: Only whitelisted media types are marked as supported
4. **Size Limits**: MMS attachments are typically capped at ~5MB per item

## Testing

### Using the Test Script

1. **Start your server**:
   ```bash
   cd DungeonMindServer
   python app.py
   ```

2. **Run the test script**:
   ```bash
   python test_mms_router.py
   ```

The test script will:
- Send sample SMS and MMS requests
- Test supported and unsupported media types
- Test webhook validation (invalid data)
- Test consistency validation (mismatched SID/NumMedia)
- Verify all endpoints are working
- Test error handling and warning generation

### Manual Testing with curl

**Test SMS:**
```bash
curl -X POST http://localhost:8000/api/sms/receive \
  -d "From=+1234567890" \
  -d "Body=Hello" \
  -d "MessageSid=SM123" \
  -d "NumMedia=0"
```

**Test MMS:**
```bash
curl -X POST http://localhost:8000/api/sms/receive \
  -d "From=+1234567890" \
  -d "Body=Check this out!" \
  -d "MessageSid=MM123" \
  -d "NumMedia=1" \
  -d "MediaUrl0=https://api.twilio.com/.../Media/ME123" \
  -d "MediaContentType0=image/jpeg"
```

**Get supported types:**
```bash
curl http://localhost:8000/api/sms/supported-media-types
```

## Integration with External APIs

### LibreChat Integration

To display media in LibreChat, the external API should:

1. **Check for media**: Look for `message_type: "MMS"` and `media` array
2. **Download if needed**: Use the provided URLs to fetch media content
3. **Display appropriately**: Show images inline, provide download links for files
4. **Handle expiration**: Download immediately if long-term storage is needed

### Example Integration Code

```python
async def process_message(payload):
    if payload.get("message_type") == "MMS":
        media_items = payload.get("media", [])
        for media in media_items:
            if media.get("supported"):
                # Download and process supported media
                content = await download_media(media["url"])
                # Store or display as appropriate
            else:
                # Log unsupported media type
                logger.warning(f"Unsupported media: {media['content_type']}")
```

## Troubleshooting

### Common Issues

1. **Missing Media**: Check that Twilio webhook includes `NumMedia` field
2. **Download Failures**: Verify Twilio credentials and URL validity
3. **Unsupported Types**: Check the supported media types list
4. **Validation Errors**: Ensure Twilio signature validation is working

### Debug Mode

Enable detailed logging by setting log level to DEBUG:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

This will show all webhook data and processing steps.

## Future Enhancements

Potential improvements:

1. **Automatic Download**: Download and store media locally
2. **Image Processing**: Resize/optimize images before forwarding
3. **Virus Scanning**: Scan uploaded files for malware
4. **Cloud Storage**: Upload media to AWS S3 or similar service
5. **Thumbnail Generation**: Create preview thumbnails for images/videos

## References

- [Twilio MMS Documentation](https://www.twilio.com/docs/sms/tutorials/how-to-receive-and-download-images-python)
- [Twilio Webhook Security](https://www.twilio.com/docs/usage/webhooks/webhooks-security)
- [FastAPI Documentation](https://fastapi.tiangolo.com/) 