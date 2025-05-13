# Speech Recognition API Server

This is a FastAPI-based REST API server that provides speech recognition and speaker identification services using Picovoice's Cheetah (for speech-to-text) and Eagle (for speaker recognition) engines.

## Features

- Real-time speech-to-text transcription
- Speaker identification
- Speaker profile enrollment
- RESTful API endpoints
- Swagger UI documentation

## Prerequisites

- Python 3.8 or higher
- Picovoice Access Key
- Docker (optional, for containerized deployment)

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd server_python
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export PICOVOICE_ACCESS_KEY="your-access-key-here"
export PROFILES_DIR="./profiles"  # Directory to store speaker profiles
```

## Running the Server

### Local Development
```bash
python api_server.py --host 0.0.0.0 --port 8000
```

### Production Deployment
For production deployment, it's recommended to use Gunicorn with Uvicorn workers:

```bash
pip install gunicorn
gunicorn api_server:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## API Endpoints

### 1. Transcribe Audio
```http
POST /transcribe
Content-Type: multipart/form-data

file: <audio_file>
```

Response:
```json
{
    "transcript": "transcribed text",
    "speaker_scores": {
        "speaker1": 0.8,
        "speaker2": 0.2
    },
    "most_likely_speaker": "speaker1"
}
```

### 2. Enroll Speaker
```http
POST /enroll?profile_name=speaker1
Content-Type: multipart/form-data

file: <audio_file>
```

Response:
```json
{
    "status": "success",
    "message": "Profile speaker1 created successfully"
}
```

### 3. List Speakers
```http
GET /speakers
```

Response:
```json
["speaker1", "speaker2", "speaker3"]
```

## API Documentation

Once the server is running, you can access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Docker Deployment

1. Build the Docker image:
```bash
docker build -t speech-recognition-api .
```

2. Run the container:
```bash
docker run -d \
    -p 8000:8000 \
    -e PICOVOICE_ACCESS_KEY="your-access-key-here" \
    -v $(pwd)/profiles:/app/profiles \
    speech-recognition-api
```

## Client Example

Here's a Python example of how to use the API:

```python
import requests

# Transcribe audio
with open('audio.wav', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/transcribe',
        files={'audio': f}
    )
print(response.json())

# Enroll speaker
with open('enrollment_audio.wav', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/enroll',
        params={'profile_name': 'john'},
        files={'audio': f}
    )
print(response.json())

# List speakers
response = requests.get('http://localhost:8000/speakers')
print(response.json())
```

## Security Considerations

For production deployment:

1. Set appropriate CORS settings in `api_server.py`
2. Use HTTPS
3. Implement authentication
4. Set up rate limiting
5. Use secure environment variables
6. Regular security updates

## License

[Your License Here]
