> **Historical import from DungeonOverMind — 2026-09-24.** This document records an older backend/deployment implementation state. It is not current DungeonMindServer architecture or sequencing authority. Re-anchor against current code/configuration before applying it.

# Learnings: CORS Configuration and Environment Variables

## Issue Encountered
While running a demo server to test a React LandingPage build on `localhost:3000`, I encountered a CORS "Missing Allow Origin" error. This error typically indicates that the server is not configured to accept requests from the client's origin.

## Root Cause
The root cause of the issue was an incorrect entry in the `ALLOWED_HOSTS` environment variable. The origin was listed as `localhost:3000` instead of `http://localhost:3000`. The missing protocol (`http://`) caused the server to reject requests from the client.

## Resolution
Updating the `ALLOWED_HOSTS` environment variable to include the correct origin with the protocol (`http://localhost:3000`) resolved the issue. This allowed the server to properly recognize and accept requests from the client.

## Key Learnings
1. **Correct Origin Format**: Always ensure that origins in CORS configurations include the protocol (e.g., `http://` or `https://`). This is crucial for the server to correctly identify and allow requests from the client.

2. **Environment Variables**: Double-check environment variables for typos or formatting issues, especially when they are used for critical configurations like CORS.

3. **Debugging CORS Issues**: Use browser developer tools to inspect network requests and responses. Look for the `Access-Control-Allow-Origin` header in the response to verify if the server is correctly configured.

4. **Explicit Configuration**: If issues persist, try explicitly setting configurations in the code to isolate and identify the problem.

By documenting this learning, I can refer back to it in the future to quickly resolve similar issues.