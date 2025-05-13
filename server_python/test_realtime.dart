import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show Duration;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';

class AudioStreamer {
  final String serverUrl;
  final recorder = Record();
  WebSocketChannel? _channel;
  Timer? _audioTimer;
  String? _tempFilePath;
  bool _isStreaming = false;
  static const int CHUNK_SIZE = 1024; // Size of audio chunks to send

  AudioStreamer(this.serverUrl);

  Future<void> startStreaming() async {
    if (_isStreaming) return;

    final wsUrl = Uri.parse('$serverUrl/stream');
    print('Connecting to: $wsUrl');

    try {
      _channel = WebSocketChannel.connect(wsUrl);
      await _channel?.ready;
      print('WebSocket connection established');

      // Initialize audio recorder
      if (await recorder.hasPermission()) {
        try {
          // Create temporary file for recording
          final tempDir = await getTemporaryDirectory();
          _tempFilePath = '${tempDir.path}/temp_audio.raw';

          // Start recording with PCM format
          await recorder.start(
            path: _tempFilePath,
            encoder: AudioEncoder.pcm16bit,
            samplingRate: 16000,
            numChannels: 1,
          );
          _isStreaming = true;
          print('Started recording to $_tempFilePath');

          // Set up timer to read and send chunks of audio data
          _audioTimer = Timer.periodic(
            const Duration(milliseconds: 32),
            (timer) async {
              if (!_isStreaming) {
                timer.cancel();
                return;
              }

              try {
                final file = File(_tempFilePath!);
                if (await file.exists()) {
                  final bytes = await file.readAsBytes();
                  if (bytes.isNotEmpty && _channel != null) {
                    // Send chunks of audio data
                    for (var i = 0; i < bytes.length; i += CHUNK_SIZE) {
                      final end = (i + CHUNK_SIZE < bytes.length)
                          ? i + CHUNK_SIZE
                          : bytes.length;
                      final chunk = bytes.sublist(i, end);
                      _channel?.sink.add(chunk);
                    }
                    // Clear the file after sending
                    await file.writeAsBytes([]);
                  }
                }
              } catch (e) {
                print('Error reading audio data: $e');
              }
            },
          );

          // Listen for responses from the server
          _channel?.stream.listen(
            (message) {
              try {
                final response = json.decode(message);
                print('Server response: $response');
              } catch (e) {
                print('Error parsing server response: $e');
              }
            },
            onError: (error) {
              print('WebSocket error: $error');
              stopStreaming();
            },
            onDone: () {
              print('WebSocket connection closed');
              stopStreaming();
            },
          );
        } catch (e) {
          print('Error starting recording: $e');
          await stopStreaming();
          rethrow;
        }
      } else {
        print('No permission to record audio');
        throw Exception('Microphone permission denied');
      }
    } catch (e) {
      print('Error establishing WebSocket connection: $e');
      await stopStreaming();
      rethrow;
    }
  }

  Future<void> stopStreaming() async {
    if (!_isStreaming) return;

    _isStreaming = false;
    _audioTimer?.cancel();

    try {
      await recorder.stop();
    } catch (e) {
      print('Error stopping recorder: $e');
    }

    try {
      await _channel?.sink.close();
    } catch (e) {
      print('Error closing WebSocket: $e');
    }
    _channel = null;

    // Clean up temporary file
    if (_tempFilePath != null) {
      try {
        final file = File(_tempFilePath!);
        if (await file.exists()) {
          await file.delete();
        }
      } catch (e) {
        print('Error cleaning up temporary file: $e');
      }
      _tempFilePath = null;
    }

    print('Stopped streaming');
  }

  Future<List<int>?> _getAudioData() async {
    try {
      // Get the temporary directory
      final tempDir = await getTemporaryDirectory();
      final tempFile = File('${tempDir.path}/temp_audio.raw');

      // Read the raw PCM data
      if (await tempFile.exists()) {
        final bytes = await tempFile.readAsBytes();
        await tempFile.delete();
        return bytes;
      }
    } catch (e) {
      print('Error reading audio data: $e');
    }
    return null;
  }
}

class ProfileManager {
  final String serverUrl;
  final int recordDurationSeconds;

  ProfileManager(this.serverUrl, {this.recordDurationSeconds = 30});

  Future<bool> registerProfile(String profileName) async {
    final recorder = Record();
    final wsUrl = Uri.parse('$serverUrl/enroll/$profileName');
    WebSocketChannel? channel;

    try {
      print('\nStarting profile registration for: $profileName');
      print('Recording for $recordDurationSeconds seconds...');

      // Connect to WebSocket
      channel = WebSocketChannel.connect(wsUrl);
      await channel.ready;
      print('WebSocket connection established');

      // Start recording
      if (await recorder.hasPermission()) {
        await recorder.start(
          encoder: AudioEncoder.pcm16bit,
          samplingRate: 16000,
          numChannels: 1,
        );

        // Listen for enrollment responses
        bool enrollmentComplete = false;
        channel.stream.listen(
          (message) {
            final response = json.decode(message);
            print('Enrollment response: $response');
            if (response['status'] == 'success') {
              enrollmentComplete = true;
            }
          },
          onError: (error) {
            print('WebSocket error: $error');
          },
        );

        // Record for specified duration
        await Future.delayed(Duration(seconds: recordDurationSeconds));

        // Stop recording and clean up
        await recorder.stop();
        await channel.sink.close();

        return enrollmentComplete;
      } else {
        print('No permission to record audio');
        return false;
      }
    } catch (e) {
      print('Error during profile registration: $e');
      await recorder.stop();
      await channel?.sink.close();
      return false;
    }
  }
}

void main() async {
  try {
    final serverUrl = 'wss://mend-server.onrender.com';
    final streamer = AudioStreamer(serverUrl);

    print('\nStarting audio streaming test...');
    await streamer.startStreaming();

    // Keep the program running until user input
    print('\nPress Enter to stop streaming...');
    await stdin.first;
    await streamer.stopStreaming();
  } catch (e, stackTrace) {
    print('Error in main: $e');
    print('Stack trace:');
    print(stackTrace);
  } finally {
    exit(0); // Ensure the program exits cleanly
  }
}
