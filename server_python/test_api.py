import requests
import os
import wave
import numpy as np

def create_test_audio(filename, duration_seconds=3, sample_rate=16000):
    """Create a test WAV file with a simple tone."""
    amplitude = 32767
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    tone = amplitude * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
    audio_data = tone.astype(np.int16)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())

def test_api():
    BASE_URL = "http://localhost:8000"
    
    # Create a test audio file
    test_audio_path = "test_audio.wav"
    create_test_audio(test_audio_path)
    
    try:
        # 1. Test speakers endpoint
        print("\nTesting /speakers endpoint...")
        response = requests.get(f"{BASE_URL}/speakers")
        print(f"Current speakers: {response.json()}")

        # 2. Test enrollment endpoint
        print("\nTesting /enroll endpoint...")
        with open(test_audio_path, 'rb') as audio_file:
            files = {'audio': audio_file}
            params = {'profile_name': 'test_speaker'}
            response = requests.post(f"{BASE_URL}/enroll", files=files, params=params)
            print(f"Enrollment response: {response.json()}")

        # 3. Test transcription endpoint
        print("\nTesting /transcribe endpoint...")
        with open(test_audio_path, 'rb') as audio_file:
            files = {'audio': audio_file}
            response = requests.post(f"{BASE_URL}/transcribe", files=files)
            print(f"Transcription response: {response.json()}")

    finally:
        # Clean up test audio file
        if os.path.exists(test_audio_path):
            os.remove(test_audio_path)

if __name__ == "__main__":
    test_api() 