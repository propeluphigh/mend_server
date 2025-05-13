import asyncio
import websockets
import wave
import time

async def test_stream():
    uri = "wss://mend-server.onrender.com/stream"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket server")
            
            # Send a simple audio frame (512 samples of silence)
            silent_frame = bytes([0] * 1024)  # 512 16-bit samples = 1024 bytes
            
            # Send a few frames
            for _ in range(5):
                await websocket.send(silent_frame)
                response = await websocket.recv()
                print(f"Received: {response}")
                time.sleep(0.1)  # Small delay between frames
                
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error: {e}")

# Run the test
asyncio.get_event_loop().run_until_complete(test_stream())