import asyncio
import websockets
import argparse
from pvrecorder import PvRecorder
import json
import struct
import time
import sys
import os
from datetime import datetime

class TranscriptionClient:
    def __init__(self, host: str, port: int, audio_device_index: int = -1):
        self.uri = f"ws://{host}:{port}"
        self.audio_device_index = audio_device_index
        self.recorder = None
        self.frame_length = 512  # Small frame length for real-time processing
        self.last_log_time = time.time()

    def _clear_line(self):
        """Clear the current line in the terminal."""
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()

    def _should_log(self):
        """Check if we should log based on time interval (1 second)."""
        current_time = time.time()
        if current_time - self.last_log_time >= 1.0:
            self.last_log_time = current_time
            return True
        return False

    async def start_transcription(self):
        try:
            # Initialize recorder
            self.recorder = PvRecorder(device_index=self.audio_device_index, frame_length=self.frame_length)
            
            # Connect to WebSocket server
            async with websockets.connect(self.uri) as websocket:
                print(f"\n🎤 Connected to transcription server at {self.uri}")
                print("Listening for speech... Press Ctrl+C to stop\n")
                
                # Start recording
                self.recorder.start()
                current_speaker = None
                
                while True:
                    # Read audio frame from microphone
                    pcm_frame = self.recorder.read()
                    
                    # Convert PCM data to bytes
                    audio_bytes = struct.pack('%dh' % len(pcm_frame), *pcm_frame)
                    
                    # Send audio data
                    await websocket.send(audio_bytes)
                    
                    # Get transcription results
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        result = json.loads(response)
                        
                        if 'error' in result:
                            print(f"\n❌ Error: {result['error']}")
                            break
                        
                        transcript = result.get('transcript', '').strip()
                        if transcript:
                            speaker = result.get('most_likely_speaker', 'Unknown')
                            scores = result.get('speaker_scores', {})
                            
                            # If speaker changed or we should log based on time
                            if speaker != current_speaker or self._should_log():
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                print(f"\n⏰ [{timestamp}]")
                                print(f"👤 Speaker: {speaker}")
                                # Format speaker scores
                                scores_str = ' | '.join(
                                    f"{name}: {score:.2f}"
                                    for name, score in scores.items()
                                )
                                print(f"📊 Confidence: {scores_str}")
                                current_speaker = speaker
                            
                            # Update transcript in place
                            self._clear_line()
                            print(f"🗣️ {transcript}", end='', flush=True)
                            
                    except asyncio.TimeoutError:
                        # No transcription received, but still log every second if needed
                        if self._should_log():
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print(f"\n⏰ [{timestamp}] Listening...")
                        continue
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping transcription...")
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
        finally:
            if self.recorder:
                self.recorder.stop()
                self.recorder.delete()

def main():
    parser = argparse.ArgumentParser(
        description='Real-time Transcription Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python realtime_transcription_client.py --host localhost --port 6789
    
Note: Make sure to enroll speakers first using eagle_enrollment_client.py
      and ensure the server is running before starting this client."""
    )
    
    parser.add_argument('--host', default='localhost', 
                       help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=6789, 
                       help='Server port (default: 6789)')
    parser.add_argument('--audio_device_index', type=int, default=-1, 
                       help='Audio device index (-1 for default)')
    
    args = parser.parse_args()
    
    client = TranscriptionClient(args.host, args.port, args.audio_device_index)
    
    try:
        asyncio.run(client.start_transcription())
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    except ConnectionRefusedError:
        print("\n❌ Error: Could not connect to the server. Make sure the server is running first.")
        print("\nTo start the server, run:")
        print("python realtime_transcription_server.py --access_key YOUR_ACCESS_KEY --profiles_dir ./profiles")

if __name__ == "__main__":
    main() 