import asyncio
import websockets
import argparse
from pvrecorder import PvRecorder
import json
import struct
import time

async def enroll_profile(websocket, recorder, profile_name):
    try:
        # Send enrollment request with profile name
        await websocket.send(json.dumps({
            'type': 'enrollment',
        }))
        
        # Send profile name
        await websocket.send(json.dumps({
            'profile_name': profile_name
        }))
        
        print("\nStarted enrollment... Keep speaking until the process completes.")
        print("The enrollment will automatically finish when enough audio is collected.")
        
        last_update_time = time.time()
        update_interval = 0.1  # Update display every 100ms
        
        while True:
            # Read audio frame from microphone
            pcm_frame = recorder.read()
            
            # Convert PCM data to bytes using struct.pack
            audio_bytes = struct.pack('%dh' % len(pcm_frame), *pcm_frame)
            
            # Send audio data
            await websocket.send(audio_bytes)
            
            # Get enrollment feedback
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                result = json.loads(response)
                
                if 'error' in result:
                    print(f"\nError: {result['error']}")
                    break
                elif 'status' in result:
                    print(f"\n{result['message']}")
                    break
                else:
                    current_time = time.time()
                    if current_time - last_update_time >= update_interval:
                        # Print enrollment progress
                        print(f"\rProgress: {result['percentage']:.1f}% - {result['feedback']}", 
                              end='', flush=True)
                        last_update_time = current_time
                    
            except asyncio.TimeoutError:
                # No feedback received, continue recording
                continue
                
    except Exception as e:
        print(f"\nError: {str(e)}")

async def main():
    parser = argparse.ArgumentParser(description='Eagle Profile Enrollment Client')
    parser.add_argument('--host', default='localhost', help='WebSocket server host')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port')
    parser.add_argument('--audio_device_index', type=int, default=-1, 
                       help='Index of input audio device (-1 for default)')
    parser.add_argument('--profile_name', required=True,
                       help='Name for the speaker profile to create')
    
    args = parser.parse_args()
    
    # Initialize audio recorder
    frame_length = 512  # Same as in original demo
    recorder = PvRecorder(device_index=args.audio_device_index, frame_length=frame_length)
    
    try:
        # Connect to WebSocket server
        uri = f"ws://{args.host}:{args.port}"
        print(f"Connecting to {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket server")
            
            # Start recording
            recorder.start()
            
            # Start enrollment process
            await enroll_profile(websocket, recorder, args.profile_name)
            
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        recorder.stop()
        recorder.delete()

if __name__ == "__main__":
    asyncio.run(main()) 