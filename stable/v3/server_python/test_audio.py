import time
from pvrecorder import PvRecorder

def main():
    try:
        devices = PvRecorder.get_audio_devices()
        print("\nAvailable Devices:")
        for i, device in enumerate(devices):
            print(f"[{i}] {device}")

        # Try each device
        for device_idx in range(len(devices)):
            print(f"\nTesting device {device_idx}: {devices[device_idx]}")
            recorder = PvRecorder(device_index=device_idx, frame_length=512)
            recorder.start()
            
            print("Recording for 5 seconds... Please speak into the microphone")
            for i in range(5):
                frame = recorder.read()
                # Calculate audio level
                audio_level = sum(abs(x) for x in frame) / len(frame)
                print(f"Audio level: {audio_level:.2f}", end='\r')
                time.sleep(1)
                
            recorder.stop()
            recorder.delete()
            print("\nDevice test complete")
            
            response = input("\nDid you hear your voice? (y/n/q to quit): ")
            if response.lower() == 'q':
                break
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main() 