import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/io.dart';

class AudioFrameGenerator {
  final int sampleRate = 16000;
  final int frameSize = 512;
  final int amplitude = 32767;
  final double baseFrequency = 440.0;
  int sampleCount = 0;

  List<int> generateFrame() {
    final samples = List<int>.filled(frameSize * 2, 0); // *2 for 16-bit samples

    for (var i = 0; i < frameSize; i++) {
      final t = (sampleCount + i) / sampleRate;
      // Create a more complex sound with multiple frequencies
      final sample = (amplitude *
              0.5 *
              (math.sin(2 * math.pi * baseFrequency * t) + // 440 Hz
                  0.5 *
                      math.sin(
                          2 * math.pi * (baseFrequency * 2) * t) + // 880 Hz
                  0.25 *
                      math.sin(2 * math.pi * (baseFrequency * 3) * t) // 1320 Hz
              ))
          .round();

      // Store as little-endian 16-bit
      samples[i * 2] = sample & 0xFF;
      samples[i * 2 + 1] = (sample >> 8) & 0xFF;
    }

    sampleCount += frameSize;
    return samples;
  }
}

Future<void> testStreamingApi({String? deployedUrl}) async {
  // For local testing use ws://, for deployed use wss://
  final wsScheme = deployedUrl != null ? 'wss' : 'ws';
  final baseUri = Uri(
    scheme: wsScheme,
    host: deployedUrl ?? 'localhost',
    port: deployedUrl != null ? null : 8000,
  );

  final generator = AudioFrameGenerator();

  print('Testing real-time streaming API');
  print('Base URI: $baseUri');

  // 1. Test enrollment
  print('\nTesting enrollment streaming...');
  WebSocketChannel? enrollWs;
  Timer? enrollTimer;

  try {
    final enrollUri = baseUri.replace(path: 'enroll/test_speaker_streaming');
    print('Attempting connection to: $enrollUri');

    enrollWs = WebSocketChannel.connect(enrollUri);
    await enrollWs.ready;
    print('WebSocket connection established for enrollment');

    enrollTimer = Timer.periodic(Duration(milliseconds: 32), (timer) {
      final frame = generator.generateFrame();
      try {
        enrollWs?.sink.add(frame);
      } catch (e) {
        print('Error sending enrollment frame: $e');
        timer.cancel();
      }
    });

    // Listen for enrollment responses
    await for (final message in enrollWs.stream) {
      final response = json.decode(message);
      print('Enrollment response: $response');

      if (response['status'] == 'success' || response['status'] == 'error') {
        enrollTimer.cancel();
        await enrollWs.sink.close();
        break;
      }
    }
  } catch (e) {
    print('Enrollment connection error: $e');
    enrollTimer?.cancel();
    await enrollWs?.sink.close();
  }

  // 2. Test transcription streaming
  print('\nTesting transcription streaming...');
  WebSocketChannel? transcribeWs;
  Timer? transcribeTimer;

  try {
    final transcribeUri = baseUri.replace(path: 'stream');
    print('Attempting connection to: $transcribeUri');

    transcribeWs = WebSocketChannel.connect(transcribeUri);
    await transcribeWs.ready;
    print('WebSocket connection established for transcription');

    transcribeTimer = Timer.periodic(Duration(milliseconds: 32), (timer) {
      final frame = generator.generateFrame();
      try {
        transcribeWs?.sink.add(frame);
      } catch (e) {
        print('Error sending transcription frame: $e');
        timer.cancel();
      }
    });

    // Listen for transcription responses
    await for (final message in transcribeWs.stream) {
      final response = json.decode(message);
      print('Transcription response: $response');
    }
  } catch (e) {
    print('Transcription connection error: $e');
  } finally {
    transcribeTimer?.cancel();
    await transcribeWs?.sink.close();
  }
}

void main() async {
  try {
    // For local testing:
    // await testStreamingApi();

    // For Render deployment:
    await testStreamingApi(deployedUrl: 'mend-server.onrender.com');
  } catch (e) {
    print('Error in main: $e');
    print('Stack trace:');
    print(StackTrace.current);
  }
}
