import 'dart:io';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:math' as math;

// Function to create test audio data (simple sine wave)
Future<void> createTestAudio(String filename,
    {int durationSeconds = 30}) async {
  final sampleRate = 16000;
  final amplitude = 32767;
  final frequency = 440.0; // 440 Hz tone
  final frameSize = 512; // Picovoice frame size requirement

  // Calculate number of frames needed for the duration
  final totalSamples = sampleRate * durationSeconds;
  final numFrames = (totalSamples / frameSize).ceil();
  final samples =
      List<int>.filled(numFrames * frameSize * 2, 0); // *2 for 16-bit samples

  for (var frame = 0; frame < numFrames; frame++) {
    for (var i = 0; i < frameSize; i++) {
      final t = (frame * frameSize + i) / sampleRate;
      // Create a more complex sound with multiple frequencies
      final sample = (amplitude *
              0.5 *
              (math.sin(2 * math.pi * frequency * t) + // 440 Hz
                  0.5 * math.sin(2 * math.pi * (frequency * 2) * t) + // 880 Hz
                  0.25 * math.sin(2 * math.pi * (frequency * 3) * t) // 1320 Hz
              ))
          .round();

      // Store as little-endian 16-bit
      final sampleIndex = (frame * frameSize + i) * 2;
      samples[sampleIndex] = sample & 0xFF;
      samples[sampleIndex + 1] = (sample >> 8) & 0xFF;
    }
  }

  final file = File(filename);
  final writer = file.openSync(mode: FileMode.write);

  final dataSize = samples.length;
  final fileSize =
      36 + dataSize; // Header (44 bytes) + data size - 8 bytes for RIFF header

  // Write WAV header
  writer.writeFromSync([
    ...utf8.encode('RIFF'), // ChunkID
    ...intToBytes(fileSize, 4), // ChunkSize
    ...utf8.encode('WAVE'), // Format
    ...utf8.encode('fmt '), // Subchunk1ID
    ...intToBytes(16, 4), // Subchunk1Size (16 for PCM)
    ...intToBytes(1, 2), // AudioFormat (1 for PCM)
    ...intToBytes(1, 2), // NumChannels (1 for mono)
    ...intToBytes(sampleRate, 4), // SampleRate
    ...intToBytes(sampleRate * 2,
        4), // ByteRate (SampleRate * NumChannels * BitsPerSample/8)
    ...intToBytes(2, 2), // BlockAlign (NumChannels * BitsPerSample/8)
    ...intToBytes(16, 2), // BitsPerSample
    ...utf8.encode('data'), // Subchunk2ID
    ...intToBytes(dataSize, 4), // Subchunk2Size
    ...samples, // Audio data
  ]);

  writer.closeSync();
}

List<int> intToBytes(int value, int length) {
  final bytes = List<int>.filled(length, 0);
  for (var i = 0; i < length; i++) {
    bytes[i] = value & 0xFF;
    value >>= 8;
  }
  return bytes;
}

Future<void> testApi() async {
  // Update this URL to your Render deployment URL
  final baseUrl = 'https://mend-server.onrender.com';
  final testAudioPath = 'test_audio.wav';

  try {
    print('Testing deployed API at: $baseUrl');

    // Create test audio file with 30 seconds duration
    await createTestAudio(testAudioPath);
    print('Created test audio file');

    // 1. Test speakers endpoint
    print('\nTesting /speakers endpoint...');
    try {
      final speakersResponse = await http.get(Uri.parse('$baseUrl/speakers'));
      print('Status code: ${speakersResponse.statusCode}');
      print('Current speakers: ${speakersResponse.body}');
    } catch (e) {
      print('Error testing speakers endpoint: $e');
    }

    // 2. Test enrollment endpoint
    print('\nTesting /enroll endpoint...');
    var enrollmentComplete = false;
    var attempts = 0;
    const maxAttempts = 3;

    while (!enrollmentComplete && attempts < maxAttempts) {
      attempts++;
      print('\nEnrollment attempt $attempts...');

      try {
        final enrollFile = await http.MultipartFile.fromPath(
          'audio',
          testAudioPath,
        );
        final enrollRequest = http.MultipartRequest(
            'POST',
            Uri.parse('$baseUrl/enroll').replace(
                queryParameters: {'profile_name': 'test_speaker_dart'}))
          ..files.add(enrollFile);

        print('Sending enrollment request...');
        final enrollResponse = await enrollRequest.send();
        print('Status code: ${enrollResponse.statusCode}');
        final enrollResult = await enrollResponse.stream.bytesToString();
        print('Enrollment response: $enrollResult');

        // Parse the response to check enrollment percentage
        if (enrollResponse.statusCode == 200) {
          final enrollJson = json.decode(enrollResult);
          if (enrollJson['status'] == 'success') {
            enrollmentComplete = true;
            break;
          }
        }
      } catch (e) {
        print('Error during enrollment attempt: $e');
      }
    }

    if (!enrollmentComplete) {
      print('\nFailed to complete enrollment after $maxAttempts attempts');
      return;
    }

    // 3. Test transcription endpoint
    print('\nTesting /transcribe endpoint...');
    try {
      final transcribeFile = await http.MultipartFile.fromPath(
        'audio',
        testAudioPath,
      );
      final transcribeRequest = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/transcribe'),
      )..files.add(transcribeFile);

      print('Sending transcription request...');
      final transcribeResponse = await transcribeRequest.send();
      print('Status code: ${transcribeResponse.statusCode}');
      final transcribeResult = await transcribeResponse.stream.bytesToString();
      print('Transcription response: $transcribeResult');
    } catch (e) {
      print('Error during transcription: $e');
    }
  } catch (e) {
    print('Error occurred: $e');
  } finally {
    // Clean up test audio file
    final testFile = File(testAudioPath);
    if (await testFile.exists()) {
      await testFile.delete();
      print('\nCleaned up test audio file');
    }
  }
}

void main() async {
  await testApi();
}
