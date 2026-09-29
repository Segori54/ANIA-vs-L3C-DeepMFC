"""WAV/FLAC preview; playback gain never changes corpus files."""
import numpy as np
import soundfile as sf
import sounddevice as sd


class AudioPreview:
    def __init__(self):
        self.stream = None
        self.data = None
        self.rate = 48000
        self.position = 0
        self.paused = False
        self.volume = 0.5

    def load(self, path):
        self.stop()
        self.data = None
        data, rate = sf.read(path, dtype='float32', always_2d=True)
        if not len(data) or not np.isfinite(data).all():
            raise ValueError('Audio vacío o con valores inválidos.')
        self.data, self.rate = data, rate

    @property
    def duration(self):
        return 0 if self.data is None else len(self.data) / self.rate

    @property
    def active(self):
        return self.stream is not None and self.stream.active

    def _callback(self, output, frames, timing, status):
        output.fill(0)
        if self.paused:
            return
        count = min(frames, len(self.data) - self.position)
        np.multiply(self.data[self.position:self.position + count], self.volume,
                    out=output[:count])
        self.position += count
        if self.position >= len(self.data):
            raise sd.CallbackStop

    def play(self):
        if self.data is None:
            return
        if self.active:
            self.paused = False
            return
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        if self.position >= len(self.data):
            self.position = 0
        self.paused = False
        try:
            self.stream = sd.OutputStream(samplerate=self.rate, channels=self.data.shape[1],
                                          dtype='float32', callback=self._callback)
            self.stream.start()
        except Exception:
            self.stop()
            raise

    def pause(self):
        if self.active:
            self.paused = not self.paused

    def stop(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self.position = 0
        self.paused = False
