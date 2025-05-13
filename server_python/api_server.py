from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import json
import os
from typing import Optional, Dict, List
import numpy as np
import pveagle
import pvcheetah
import struct
from pydantic import BaseModel
from fastapi import WebSocketDisconnect

class TranscriptionResponse(BaseModel):
    transcript: str
    speaker_scores: Dict[str, float]
    most_likely_speaker: str

class EnrollmentResponse(BaseModel):
    status: str
    message: str

app = FastAPI(
    title="Speech Recognition API",
    description="API for real-time transcription and speaker recognition",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add WebSocket exception handler
@app.exception_handler(WebSocketDisconnect)
async def websocket_disconnect_handler(request: Request, exc: WebSocketDisconnect):
    print(f"WebSocket client disconnected with code: {exc.code}")
    return None

class SpeechProcessor:
    def __init__(self, access_key: str, profiles_dir: str):
        self.access_key = access_key
        self.profiles_dir = profiles_dir
        self.eagle = None
        self.cheetah = None
        self.speaker_labels = []
        self.profiles = []
        self._load_profiles()  # Only load profiles initially
        
    def _load_profiles(self):
        """Load speaker profiles without initializing engines"""
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir)
            
        self.speaker_labels = []
        self.profiles = []
        
        for profile_file in os.listdir(self.profiles_dir):
            if profile_file.endswith('.bin'):
                profile_path = os.path.join(self.profiles_dir, profile_file)
                self.speaker_labels.append(os.path.splitext(profile_file)[0])
                with open(profile_path, 'rb') as f:
                    profile = pveagle.EagleProfile.from_bytes(f.read())
                self.profiles.append(profile)

    def _ensure_cheetah_initialized(self):
        """Lazy initialization of Cheetah"""
        if self.cheetah is None:
            self.cheetah = pvcheetah.create(
                access_key=self.access_key,
                endpoint_duration_sec=0.5,
                enable_automatic_punctuation=True
            )

    def _ensure_eagle_initialized(self):
        """Lazy initialization of Eagle"""
        if self.eagle is None and self.profiles:
            self.eagle = pveagle.create_recognizer(
                access_key=self.access_key,
                speaker_profiles=self.profiles
            )

    def process_frame(self, frame_data: bytes) -> Optional[TranscriptionResponse]:
        # Convert bytes to PCM data (assuming 16-bit audio)
        pcm_data = list(struct.unpack('h' * (len(frame_data) // 2), frame_data))
        
        if len(pcm_data) != 512:  # Ensure frame size is correct
            return None

        # Process speaker identification
        speaker_scores = {}
        most_likely_speaker = "Unknown"
        
        try:
            self._ensure_eagle_initialized()
            if self.eagle:
                scores = self.eagle.process(pcm_data)
                speaker_scores = {
                    label: float(score) 
                    for label, score in zip(self.speaker_labels, scores)
                }
                if speaker_scores:
                    most_likely_speaker = max(speaker_scores.items(), key=lambda x: x[1])[0]
        except Exception as e:
            print(f"Speaker identification error: {str(e)}")
            # Reset eagle on error
            self.eagle = None

        # Process transcription
        transcript = ""
        try:
            self._ensure_cheetah_initialized()
            partial_transcript, is_endpoint = self.cheetah.process(pcm_data)
            if partial_transcript or is_endpoint:
                transcript = partial_transcript
                if is_endpoint:
                    remaining_text = self.cheetah.flush()
                    if remaining_text:
                        transcript += " " + remaining_text
        except Exception as e:
            print(f"Transcription error: {str(e)}")
            # Reset cheetah on error
            self.cheetah = None

        if transcript or speaker_scores:
            return TranscriptionResponse(
                transcript=transcript.strip(),
                speaker_scores=speaker_scores,
                most_likely_speaker=most_likely_speaker
            )
        return None

    async def process_stream(self, websocket: WebSocket) -> None:
        try:
            while True:
                frame_data = await websocket.receive_bytes()
                result = self.process_frame(frame_data)
                if result:
                    await websocket.send_json(result.dict())
        except Exception as e:
            print(f"Stream processing error: {str(e)}")
        finally:
            # Clean up resources
            if self.cheetah:
                self.cheetah = None
            if self.eagle:
                self.eagle = None

    async def enroll_speaker(self, profile_name: str, websocket: WebSocket) -> None:
        try:
            eagle_profiler = pveagle.create_profiler(access_key=self.access_key)
            
            while True:
                try:
                    frame_data = await websocket.receive_bytes()
                    pcm_data = list(struct.unpack('h' * (len(frame_data) // 2), frame_data))
                    
                    if len(pcm_data) != 512:  # Ensure frame size is correct
                        await websocket.send_json({
                            "status": "error",
                            "message": "Invalid frame size"
                        })
                        continue

                    enroll_percentage, feedback = eagle_profiler.enroll(pcm_data)
                    
                    await websocket.send_json({
                        "status": "progress",
                        "percentage": enroll_percentage,
                        "feedback": feedback
                    })
                    
                    if enroll_percentage >= 100.0:
                        # Export and save profile
                        profile = eagle_profiler.export()
                        profile_path = os.path.join(self.profiles_dir, f"{profile_name}.bin")
                        
                        with open(profile_path, 'wb') as f:
                            f.write(profile.to_bytes())
                        
                        # Update processor state
                        self.speaker_labels.append(profile_name)
                        self.profiles.append(profile)
                        
                        # Reinitialize recognizer
                        self.eagle = pveagle.create_recognizer(
                            access_key=self.access_key,
                            speaker_profiles=self.profiles
                        )
                        
                        await websocket.send_json({
                            "status": "success",
                            "message": f"Profile {profile_name} created successfully"
                        })
                        break

                except Exception as e:
                    await websocket.send_json({
                        "status": "error",
                        "message": f"Error during enrollment: {str(e)}"
                    })
                    break
                    
        finally:
            if 'eagle_profiler' in locals():
                eagle_profiler.delete()

# Global processor instance
speech_processor = None

@app.on_event("startup")
async def startup_event():
    global speech_processor
    access_key = os.getenv("PICOVOICE_ACCESS_KEY")
    profiles_dir = os.getenv("PROFILES_DIR", "./profiles")
    
    if not access_key:
        raise ValueError("PICOVOICE_ACCESS_KEY environment variable not set")
    
    speech_processor = SpeechProcessor(access_key, profiles_dir)

@app.websocket("/stream")
async def stream_audio(websocket: WebSocket):
    if not speech_processor:
        await websocket.close(code=1011, reason="Speech processor not initialized")
        return
    
    print(f"New streaming connection request from {websocket.client}")    
    try:
        await websocket.accept()
        print(f"Streaming connection accepted for {websocket.client}")
        await speech_processor.process_stream(websocket)
    except WebSocketDisconnect:
        print(f"Client {websocket.client} disconnected from streaming")
    except Exception as e:
        print(f"Error in streaming connection: {e}")
        if not websocket.client_state.DISCONNECTED:
            await websocket.close(code=1011)

@app.websocket("/enroll/{profile_name}")
async def enroll_speaker(websocket: WebSocket, profile_name: str):
    if not speech_processor:
        await websocket.close(code=1011, reason="Speech processor not initialized")
        return
    
    print(f"New enrollment connection request from {websocket.client} for profile {profile_name}")
    try:
        await websocket.accept()
        print(f"Enrollment connection accepted for {websocket.client}")
        await speech_processor.enroll_speaker(profile_name, websocket)
    except WebSocketDisconnect:
        print(f"Client {websocket.client} disconnected from enrollment")
    except Exception as e:
        print(f"Error in enrollment connection: {e}")
        if not websocket.client_state.DISCONNECTED:
            await websocket.close(code=1011)

@app.get("/speakers")
async def list_speakers() -> List[str]:
    if not speech_processor:
        raise HTTPException(status_code=500, detail="Speech processor not initialized")
    return speech_processor.speaker_labels

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "Speech Recognition API Server",
        "available_endpoints": [
            "/health",
            "/speakers",
            "/stream (WebSocket)",
            "/enroll/{profile_name} (WebSocket)"
        ]
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Speech Recognition API Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8001')), help='Port to bind the server to')
    
    args = parser.parse_args()
    
    # Configure logging
    uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Run with production settings and WebSocket support
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
        ws_ping_interval=20.0,  # Send ping frames every 20 seconds
        ws_ping_timeout=20.0,   # Wait 20 seconds for pong response
        ws='websockets'         # Use websockets package for WebSocket support
    )

if __name__ == "__main__":
    main() 