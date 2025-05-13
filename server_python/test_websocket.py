import asyncio
import websockets
import json

async def test_websocket_connection():
    uri = "wss://mend-server.onrender.com/stream"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket server")
            
            # Wait for initial connection message
            response = await websocket.recv()
            print("Initial response:", response)
            
            # Create a silent audio frame (512 samples of silence)
            silent_frame = bytes([0] * 1024)  # 512 16-bit samples = 1024 bytes
            
            # Send 5 test frames
            for i in range(5):
                print(f"\nSending frame {i+1}")
                await websocket.send(silent_frame)
                
                # Wait for response
                response = await websocket.recv()
                print(f"Response {i+1}:", response)
                
                # Small delay between frames
                await asyncio.sleep(0.1)
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"Failed to connect: {e}")
        print("Make sure the WebSocket endpoint is available and the server is running")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: code = {e.code}, reason = {e.reason}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    print("Testing WebSocket connection to /stream endpoint...")
    asyncio.get_event_loop().run_until_complete(test_websocket_connection()) 