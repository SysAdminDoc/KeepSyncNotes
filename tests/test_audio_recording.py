import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

import keepsync_audio_recording as audio
import keepsync_notes as app


class FakeRawStream:
    def __init__(self, callback):
        self.callback = callback
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True
        self.callback(b"\x01\x00" * 160, 160, None, None)

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class AudioRecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "notes.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_audio_attachment_writes_wav_under_note_directory(self):
        attachment = audio.save_audio_attachment(
            [b"\x00\x00" * 320],
            self.db_path,
            "note-1",
            filename="recording.wav",
        )

        stored = Path(attachment.stored_path)
        self.assertTrue(stored.exists())
        self.assertEqual(stored.parent, self.root / "attachments" / "note-1")
        self.assertEqual(attachment.mime_type, "audio/wav")
        with wave.open(str(stored), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), audio.DEFAULT_AUDIO_CHANNELS)
            self.assertEqual(wav_file.getframerate(), audio.DEFAULT_AUDIO_SAMPLE_RATE)
            self.assertGreater(wav_file.getnframes(), 0)

    def test_audio_recorder_uses_stream_factory_and_saves_attachment(self):
        streams = []

        def factory(callback):
            stream = FakeRawStream(callback)
            streams.append(stream)
            return stream

        recorder = audio.AudioRecorder(stream_factory=factory)
        recorder.start()
        attachment = recorder.stop_to_attachment(self.db_path, "note-2")

        self.assertFalse(recorder.is_recording)
        self.assertTrue(streams[0].started)
        self.assertTrue(streams[0].stopped)
        self.assertTrue(streams[0].closed)
        self.assertTrue(Path(attachment.stored_path).exists())

    def test_transcribe_audio_file_uses_model_factory_segments(self):
        def factory(model_name):
            self.assertEqual(model_name, audio.DEFAULT_WHISPER_MODEL)
            return SimpleNamespace(
                transcribe=lambda path: (
                    [SimpleNamespace(text=" hello "), SimpleNamespace(text="world")],
                    SimpleNamespace(),
                )
            )

        transcript = audio.transcribe_audio_file(self.root / "voice.wav", model_factory=factory)

        self.assertEqual(transcript, "hello world")

    def test_append_audio_transcript_adds_inline_block(self):
        text = audio.append_audio_transcript("Existing note", " recorded words ")

        self.assertEqual(text, "Existing note\n\nAudio transcript:\nrecorded words")

    def test_app_reexports_audio_helpers_for_compatibility(self):
        self.assertIs(app.AudioRecorder, audio.AudioRecorder)
        self.assertIs(app.save_audio_attachment, audio.save_audio_attachment)
        self.assertIs(app.transcribe_audio_file, audio.transcribe_audio_file)
        self.assertIs(app.append_audio_transcript, audio.append_audio_transcript)


if __name__ == "__main__":
    unittest.main()
