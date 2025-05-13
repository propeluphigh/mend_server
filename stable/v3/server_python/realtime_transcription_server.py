import asyncio
import json
import websockets
import numpy as np
import pveagle
import pvcheetah
import os
import struct
from typing import List, Dict
from collections import deque

class RealtimeTranscriptionServer:
    def __init__(self, access_key: str, profiles_dir: str):
        self.access_key = access_key
        self.profiles_dir = profiles_dir
        self.eagle = None
        self.cheetah = None
        self.speaker_labels = []
        self.profiles = []
        self.initialize_engines()
        
        # Buffer settings optimized for Cheetah
        self.frame_length = None  # Will be set by Cheetah's requirements

    def initialize_engines(self):
        # Initialize Cheetah for real-time speech-to-text
        self.cheetah = pvcheetah.create(
            access_key=self.access_key,
            endpoint_duration_sec=0.5,  # Shorter endpoint duration for faster responses
            enable_automatic_punctuation=True
        )
        self.frame_length = self.cheetah.frame_length

        # Load all speaker profiles from the profiles directory
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

    async def process_audio(self, websocket):
        try:
            while True:
                # Receive audio data as bytes
                audio_data = await websocket.recv()
                
                # Convert bytes to PCM data
                pcm_data = list(struct.unpack('h' * (len(audio_data) // 2), audio_data))
                
                # Process speaker identification with Eagle
                speaker_scores = {}
                most_likely_speaker = "Unknown"
                if self.eagle and len(pcm_data) > 0:
                    scores = self.eagle.process(pcm_data)
                    speaker_scores = {
                        label: float(score) 
                        for label, score in zip(self.speaker_labels, scores)
                    }
                    if speaker_scores:
                        most_likely_speaker = max(speaker_scores.items(), key=lambda x: x[1])[0]

                # Process speech-to-text with Cheetah
                transcript, is_endpoint = self.cheetah.process(pcm_data)
                
                # If we hit an endpoint, get any remaining text
                if is_endpoint:
                    remaining_text = self.cheetah.flush()
                    if remaining_text:
                        transcript += " " + remaining_text
                
                # Send back combined results
                response = {
                    'speaker_scores': speaker_scores,
                    'most_likely_speaker': most_likely_speaker,
                    'transcript': transcript.strip()
                }
                
                await websocket.send(json.dumps(response))

        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected")
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
            try:
                await websocket.send(json.dumps({'error': str(e)}))
            except:
                pass
        finally:
            if self.cheetah:
                self.cheetah.delete()

    async def start_server(self, host: str = 'localhost', port: int = 6789):
        if not self.profiles:
            print("Warning: No speaker profiles loaded. Speaker identification will not work.")
            print("Please enroll speakers first using eagle_enrollment_client.py")
        
        print(f"Transcription server started at ws://{host}:{port}")
        print(f"Loaded {len(self.profiles)} speaker profiles")
        print(f"Using Cheetah frame length: {self.frame_length}")
        print("Processing audio in real-time with minimal latency")
        
        async with websockets.serve(self.process_audio, host, port):
            await asyncio.Future()  # run forever

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Real-time Transcription Server with Speaker Recognition')
    parser.add_argument('--access_key', required=True, help='AccessKey for Picovoice services')
    parser.add_argument('--profiles_dir', required=True, help='Directory containing speaker profiles')
    parser.add_argument('--host', default='localhost', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=6789, help='Port to bind the server to')
    
    args = parser.parse_args()
    
    server = RealtimeTranscriptionServer(args.access_key, args.profiles_dir)
    asyncio.run(server.start_server(args.host, args.port))

if __name__ == "__main__":
    main() 