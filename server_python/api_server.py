from fastapi import FastAPI, File, UploadFile, HTTPException
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
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SpeechProcessor:
    def __init__(self, access_key: str, profiles_dir: str):
        self.access_key = access_key
        self.profiles_dir = profiles_dir
        self.eagle = None
        self.cheetah = None
        self.speaker_labels = []
        self.profiles = []
        self.initialize_engines()

    def initialize_engines(self):
        # Initialize Cheetah
        self.cheetah = pvcheetah.create(
            access_key=self.access_key,
            endpoint_duration_sec=0.5,
            enable_automatic_punctuation=True
        )

        # Load speaker profiles
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

    def process_audio(self, audio_data: bytes) -> TranscriptionResponse:
        # Skip WAV header (44 bytes) to get to PCM data
        pcm_data = list(struct.unpack('h' * ((len(audio_data) - 44) // 2), audio_data[44:]))
        
        # Process speaker identification
        speaker_scores = {}
        most_likely_speaker = "Unknown"
        if self.eagle and len(pcm_data) > 0:
            try:
                scores = self.eagle.process(pcm_data)
                speaker_scores = {
                    label: float(score) 
                    for label, score in zip(self.speaker_labels, scores)
                }
                if speaker_scores:
                    most_likely_speaker = max(speaker_scores.items(), key=lambda x: x[1])[0]
            except Exception as e:
                print(f"Speaker identification error: {str(e)}")

        # Process transcription
        transcript = ""
        try:
            transcript, is_endpoint = self.cheetah.process(pcm_data)
            if is_endpoint:
                remaining_text = self.cheetah.flush()
                if remaining_text:
                    transcript += " " + remaining_text
        except Exception as e:
            print(f"Transcription error: {str(e)}")
            transcript = "Error processing audio"

        return TranscriptionResponse(
            transcript=transcript.strip(),
            speaker_scores=speaker_scores,
            most_likely_speaker=most_likely_speaker
        )

    async def enroll_speaker(self, profile_name: str, audio_data: bytes) -> EnrollmentResponse:
        try:
            eagle_profiler = pveagle.create_profiler(access_key=self.access_key)
            # Skip WAV header (44 bytes) to get to PCM data
            pcm_data = list(struct.unpack('h' * ((len(audio_data) - 44) // 2), audio_data[44:]))
            
            # Process enrollment
            try:
                enroll_percentage, feedback = eagle_profiler.enroll(pcm_data)
                
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
                    
                    return EnrollmentResponse(
                        status="success",
                        message=f"Profile {profile_name} created successfully"
                    )
                else:
                    return EnrollmentResponse(
                        status="incomplete",
                        message=f"Enrollment at {enroll_percentage:.1f}%. More audio needed."
                    )
            except Exception as e:
                return EnrollmentResponse(
                    status="error",
                    message=f"Error during enrollment: {str(e)}"
                )
                
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

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(audio: UploadFile = File(...)):
    if not speech_processor:
        raise HTTPException(status_code=500, detail="Speech processor not initialized")
    
    audio_data = await audio.read()
    return speech_processor.process_audio(audio_data)

@app.post("/enroll", response_model=EnrollmentResponse)
async def enroll_speaker(profile_name: str, audio: UploadFile = File(...)):
    if not speech_processor:
        raise HTTPException(status_code=500, detail="Speech processor not initialized")
    
    audio_data = await audio.read()
    return await speech_processor.enroll_speaker(profile_name, audio_data)

@app.get("/speakers")
async def list_speakers() -> List[str]:
    if not speech_processor:
        raise HTTPException(status_code=500, detail="Speech processor not initialized")
    return speech_processor.speaker_labels

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Speech Recognition API Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8000')), help='Port to bind the server to')
    
    args = parser.parse_args()
    
    # Configure logging
    uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Run with production settings
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*"
    )

if __name__ == "__main__":
    main() 