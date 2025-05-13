import asyncio
import websockets
import argparse
from pvrecorder import PvRecorder
import json
import struct

async def send_audio_stream(websocket, recorder, frame_length):
    try:
        # Send connection type
        await websocket.send(json.dumps({
            'type': 'recognition'
        }))
        
        print("Started streaming audio... Press Ctrl+C to stop")
        while True:
            # Read audio frame from microphone
            pcm_frame = recorder.read()
            
            # Convert PCM data to bytes using struct.pack
            audio_bytes = struct.pack('%dh' % len(pcm_frame), *pcm_frame)
            
            # Send audio data
            await websocket.send(audio_bytes)
            
            # Receive and print results
            response = await websocket.recv()
            results = json.loads(response)
            
            if 'error' in results:
                print(f"\rError: {results['error']}", end='', flush=True)
            else:
                # Print speaker recognition scores
                scores_str = ' | '.join(f"{speaker}: {score:.2f}" 
                                      for speaker, score in results['scores'].items())
                print(f"\rScores: {scores_str}", end='', flush=True)
                
    except KeyboardInterrupt:
        print("\nStopping audio stream...")
    except Exception as e:
        print(f"\nError: {str(e)}")

async def main():
    parser = argparse.ArgumentParser(description='Eagle WebSocket Client Demo')
    parser.add_argument('--host', default='localhost', help='WebSocket server host')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port')
    parser.add_argument('--audio_device_index', type=int, default=-1, 
                       help='Index of input audio device (-1 for default)')
    
    args = parser.parse_args()
    
    # Initialize audio recorder
    frame_length = 512  # Same as in original demo
    recorder = PvRecorder(device_index=args.audio_device_index, frame_length=frame_length)
    
    try:
        # Connect to WebSocket server
        uri = f"ws://{args.host}:{args.port}"
        print(f"Connecting to {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print(f"Connected to WebSocket server")
            
            # Start recording
            recorder.start()
            
            # Start sending audio stream
            await send_audio_stream(websocket, recorder, frame_length)
            
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        recorder.stop()
        recorder.delete()

if __name__ == "__main__":
    asyncio.run(main()) 