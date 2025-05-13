import asyncio
import json
import websockets
import numpy as np
import pveagle
import os
import struct
from typing import List, Dict

class EagleWebSocketServer:
    def __init__(self, access_key: str, profiles_dir: str):
        self.access_key = access_key
        self.profiles_dir = profiles_dir
        self.eagle = None
        self.speaker_labels = []
        self.profiles = []
        self.initialize_eagle()

    def initialize_eagle(self):
        # Load all profiles from the profiles directory
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir)
            
        for profile_file in os.listdir(self.profiles_dir):
            if profile_file.endswith('.bin'):
                profile_path = os.path.join(self.profiles_dir, profile_file)
                self.speaker_labels.append(os.path.splitext(profile_file)[0])
                with open(profile_path, 'rb') as f:
                    profile = pveagle.EagleProfile.from_bytes(f.read())
                self.profiles.append(profile)

        if self.profiles:
            self.eagle = pveagle.create_recognizer(
                access_key=self.access_key,
                speaker_profiles=self.profiles
            )

    async def handle_enrollment(self, websocket):
        try:
            # Create profiler instance
            eagle_profiler = pveagle.create_profiler(access_key=self.access_key)
            enroll_percentage = 0.0
            last_feedback = None
            
            # Get profile name from client
            msg = await websocket.recv()
            profile_data = json.loads(msg)
            profile_name = profile_data.get('profile_name')
            
            if not profile_name:
                await websocket.send(json.dumps({
                    'error': 'Profile name not provided'
                }))
                return
                
            print(f"Starting enrollment for profile: {profile_name}")
            
            # Calculate minimum samples needed
            min_samples = eagle_profiler.min_enroll_samples
            accumulated_samples = []
            
            while enroll_percentage < 100.0:
                # Receive audio data
                audio_data = await websocket.recv()
                pcm_data = list(struct.unpack('h' * (len(audio_data) // 2), audio_data))
                accumulated_samples.extend(pcm_data)
                
                # Process enrollment with accumulated samples
                if len(accumulated_samples) >= min_samples:
                    enroll_percentage, feedback = eagle_profiler.enroll(accumulated_samples)
                    accumulated_samples = []  # Clear accumulated samples after processing
                else:
                    # Still collecting samples
                    enroll_percentage = (len(accumulated_samples) / min_samples) * 100
                    feedback = pveagle.EagleProfilerEnrollFeedback.AUDIO_TOO_SHORT
                
                # Only send feedback if there's a change
                if feedback != last_feedback or len(accumulated_samples) == 0:
                    response = {
                        'percentage': enroll_percentage,
                        'feedback': FEEDBACK_TO_DESCRIPTIVE_MSG.get(feedback, str(feedback))
                    }
                    await websocket.send(json.dumps(response))
                    last_feedback = feedback
            
            # Export and save profile
            profile = eagle_profiler.export()
            profile_path = os.path.join(self.profiles_dir, f"{profile_name}.bin")
            
            with open(profile_path, 'wb') as f:
                f.write(profile.to_bytes())
            
            # Update server state
            self.speaker_labels.append(profile_name)
            self.profiles.append(profile)
            
            # Reinitialize recognizer with new profile
            self.eagle = pveagle.create_recognizer(
                access_key=self.access_key,
                speaker_profiles=self.profiles
            )
            
            await websocket.send(json.dumps({
                'status': 'success',
                'message': f'Profile {profile_name} created successfully'
            }))
            
        except Exception as e:
            print(f"Error during enrollment: {str(e)}")
            await websocket.send(json.dumps({
                'error': str(e)
            }))
        finally:
            if 'eagle_profiler' in locals():
                eagle_profiler.delete()

    async def process_audio(self, websocket):
        try:
            while True:
                # Receive audio data as bytes
                audio_data = await websocket.recv()
                
                # Convert bytes to PCM data
                pcm_data = struct.unpack('h' * (len(audio_data) // 2), audio_data)
                
                # Process the audio with Eagle
                if self.eagle:
                    scores = self.eagle.process(pcm_data)
                    
                    # Create response with speaker scores
                    response = {
                        'scores': {
                            label: float(score) 
                            for label, score in zip(self.speaker_labels, scores)
                        }
                    }
                    
                    # Send back the results
                    await websocket.send(json.dumps(response))
                else:
                    await websocket.send(json.dumps({
                        'error': 'No speaker profiles loaded'
                    }))

        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected")
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
            try:
                await websocket.send(json.dumps({'error': str(e)}))
            except:
                pass

    async def handle_connection(self, websocket):
        try:
            # Get connection type from client
            msg = await websocket.recv()
            connection_data = json.loads(msg)
            connection_type = connection_data.get('type', 'recognition')
            
            if connection_type == 'enrollment':
                await self.handle_enrollment(websocket)
            else:  # recognition
                await self.process_audio(websocket)
                
        except Exception as e:
            print(f"Error handling connection: {str(e)}")
            try:
                await websocket.send(json.dumps({'error': str(e)}))
            except:
                pass

    async def start_server(self, host: str = 'localhost', port: int = 8765):
        async with websockets.serve(self.handle_connection, host, port):
            print(f"WebSocket server started at ws://{host}:{port}")
            await asyncio.Future()  # run forever

# Feedback messages from original demo
FEEDBACK_TO_DESCRIPTIVE_MSG = {
    pveagle.EagleProfilerEnrollFeedback.AUDIO_OK: 'Good audio',
    pveagle.EagleProfilerEnrollFeedback.AUDIO_TOO_SHORT: 'Insufficient audio length',
    pveagle.EagleProfilerEnrollFeedback.UNKNOWN_SPEAKER: 'Different speaker in audio',
    pveagle.EagleProfilerEnrollFeedback.NO_VOICE_FOUND: 'No voice found in audio',
    pveagle.EagleProfilerEnrollFeedback.QUALITY_ISSUE: 'Low audio quality due to bad microphone or environment'
}

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Eagle WebSocket Server')
    parser.add_argument('--access_key', required=True, help='AccessKey for Eagle')
    parser.add_argument('--profiles_dir', required=True, help='Directory containing speaker profiles')
    parser.add_argument('--host', default='localhost', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=8765, help='Port to bind the server to')
    
    args = parser.parse_args()
    
    server = EagleWebSocketServer(args.access_key, args.profiles_dir)
    
    asyncio.run(server.start_server(args.host, args.port))

if __name__ == "__main__":
    main() 