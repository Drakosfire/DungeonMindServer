# Performance Investigation: 24-Second Delay in Streaming

## Problem
The `client.chat.completions.create()` call with `stream=True` is taking 24 seconds to return, even though:
- HTTP request goes out immediately (per httpx logs)
- Preprocessing completes in ~85ms
- The function should return immediately with a stream object

## Timeline Analysis
```
Request received: T0
Preprocessing starts: T0 + ~0ms
Preprocessing ends: T0 + ~85ms
About to call create(): T0 + ~85ms
HTTP Request sent (httpx): T0 + ~85ms (immediate)
create() returns: T0 + ~24048ms (24 seconds later!)
Stream thread starts: T0 + ~24050ms
```

## Root Cause Hypothesis

### Hypothesis 1: Synchronous Function Blocking Event Loop
- `generate_bot_response_stream()` is synchronous
- Called from async FastAPI endpoint
- All preprocessing happens synchronously before stream generator is created
- The OpenAI call might be blocking the event loop

### Hypothesis 2: OpenAI SDK Waiting for First Chunk
- The SDK might be waiting for the first chunk before returning stream object
- But httpx logs show HTTP request goes out immediately
- This doesn't match the behavior

### Hypothesis 3: Thread/Event Loop Contention
- Synchronous function running in async context
- Possible GIL (Global Interpreter Lock) contention
- Or event loop blocking

## Current Implementation Issues

1. **Synchronous Function in Async Context**
   - `generate_bot_response_stream()` is `def`, not `async def`
   - Called from `async def query_rules()`
   - All preprocessing blocks the event loop

2. **Stream Generator Created After Preprocessing**
   - Preprocessing (semantic search, prompt formatting) happens synchronously
   - Stream generator is created after all preprocessing
   - This delays when streaming can start

3. **OpenAI Call Blocking**
   - `client.chat.completions.create()` call is synchronous
   - Even with `stream=True`, it's blocking for 24 seconds
   - This suggests the SDK might be doing something synchronous

## Proposed Solutions

### Solution 1: Make Function Async
- Convert `generate_bot_response_stream()` to `async def`
- Use `asyncio.to_thread()` for blocking operations (semantic search, OpenAI call)
- This allows the event loop to continue processing

### Solution 2: Move Preprocessing to Background
- Start preprocessing in background thread
- Return stream generator immediately
- Stream generator waits for preprocessing to complete

### Solution 3: Use Async OpenAI Client
- Check if OpenAI SDK has async version
- Use `AsyncOpenAI` instead of `OpenAI`
- This would be the cleanest solution

## Next Steps

1. Add detailed timing around OpenAI call
2. Check if OpenAI SDK has async version
3. Convert function to async if needed
4. Test with async patterns

## Files Modified
- `ruleslawyer_helper.py`: Added detailed timing instrumentation
- Added thread pool executor for OpenAI call (experimental)

