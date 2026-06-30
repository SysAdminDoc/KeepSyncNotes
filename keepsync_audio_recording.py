"""Audio recording and local transcription helpers."""

from pathlib import Path
from typing import Callable, Iterable, List, Optional
import threading
import uuid
import wave

from keepsync_attachment_editing import note_attachment_dir, unique_attachment_path
from keepsync_models import Attachment


AUDIO_MIME_TYPE = "audio/wav"
DEFAULT_AUDIO_SAMPLE_RATE = 16000
DEFAULT_AUDIO_CHANNELS = 1
DEFAULT_AUDIO_SAMPLE_WIDTH = 2
DEFAULT_WHISPER_MODEL = "base"


class AudioRecordingError(RuntimeError):
    pass


class AudioTranscriptionError(RuntimeError):
    pass


class AudioRecorder:
    """Small sounddevice-backed raw PCM recorder."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
        channels: int = DEFAULT_AUDIO_CHANNELS,
        sample_width: int = DEFAULT_AUDIO_SAMPLE_WIDTH,
        stream_factory: Optional[Callable[[Callable], object]] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self._stream_factory = stream_factory
        self._stream = None
        self._chunks: List[bytes] = []
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self):
        if self._stream is not None:
            raise AudioRecordingError("Audio recording is already active.")

        self._chunks = []

        def callback(indata, frames, time_info, status):
            chunk = bytes(indata)
            if chunk:
                with self._lock:
                    self._chunks.append(chunk)

        try:
            self._stream = self._create_stream(callback)
            self._stream.start()
        except Exception as e:
            self._stream = None
            raise AudioRecordingError(f"Could not start microphone recording: {e}") from e

    def _create_stream(self, callback: Callable):
        if self._stream_factory:
            return self._stream_factory(callback)

        try:
            import sounddevice as sd
        except Exception as e:
            raise AudioRecordingError("The sounddevice package is required for recording.") from e

        return sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=callback,
        )

    def stop(self) -> List[bytes]:
        if self._stream is None:
            raise AudioRecordingError("Audio recording is not active.")

        stream = self._stream
        try:
            stream.stop()
        finally:
            stream.close()
            self._stream = None

        with self._lock:
            chunks = list(self._chunks)
            self._chunks = []

        if not chunks:
            raise AudioRecordingError("No audio samples were captured.")
        return chunks

    def stop_to_attachment(self, db_path: str, note_id: str, filename: Optional[str] = None) -> Attachment:
        chunks = self.stop()
        return save_audio_attachment(
            chunks,
            db_path,
            note_id,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
            filename=filename,
        )


def save_audio_attachment(
    chunks: Iterable[bytes],
    db_path: str,
    note_id: str,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    channels: int = DEFAULT_AUDIO_CHANNELS,
    sample_width: int = DEFAULT_AUDIO_SAMPLE_WIDTH,
    filename: Optional[str] = None,
) -> Attachment:
    audio_chunks = [bytes(chunk) for chunk in chunks if chunk]
    if not audio_chunks:
        raise AudioRecordingError("No audio samples were captured.")

    target_dir = note_attachment_dir(db_path, note_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_attachment_path(target_dir, filename or f"voice-{uuid.uuid4().hex}.wav")
    write_wav_file(target, audio_chunks, sample_rate, channels, sample_width)
    return Attachment(filename=target.name, stored_path=str(target), mime_type=AUDIO_MIME_TYPE)


def write_wav_file(
    path: Path,
    chunks: Iterable[bytes],
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    channels: int = DEFAULT_AUDIO_CHANNELS,
    sample_width: int = DEFAULT_AUDIO_SAMPLE_WIDTH,
):
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        for chunk in chunks:
            wav_file.writeframes(chunk)


def transcribe_audio_file(
    audio_path: Path,
    model_name: str = DEFAULT_WHISPER_MODEL,
    model_factory: Optional[Callable[[str], object]] = None,
) -> str:
    try:
        if model_factory is None:
            from faster_whisper import WhisperModel

            model_factory = lambda name: WhisperModel(name, device="cpu", compute_type="int8")
        model = model_factory(model_name)
        segments, _ = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    except Exception as e:
        raise AudioTranscriptionError(f"Could not transcribe audio: {e}") from e


def append_audio_transcript(existing_text: str, transcript: str) -> str:
    text = transcript.strip()
    if not text:
        return existing_text
    existing = existing_text.rstrip()
    separator = "\n\n" if existing else ""
    return f"{existing}{separator}Audio transcript:\n{text}"
