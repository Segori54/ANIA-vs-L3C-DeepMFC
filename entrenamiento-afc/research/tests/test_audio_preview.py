import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
import sounddevice as sd
from afc_lab.audio_preview import AudioPreview


class PreviewTests(unittest.TestCase):
    def test_pause_gain_end_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'voice.flac'
            sf.write(path, np.full(100, 0.25), 48000, subtype='PCM_24')
            original = path.read_bytes()
            player = AudioPreview()
            player.load(path)
            player.paused = True
            out = np.ones((64, 1), dtype='float32')
            player._callback(out, 64, None, None)
            self.assertEqual(player.position, 0)
            self.assertTrue((out == 0).all())
            player.paused = False
            player._callback(out, 64, None, None)
            np.testing.assert_allclose(out, 0.125)
            with self.assertRaises(sd.CallbackStop):
                player._callback(out, 64, None, None)
            np.testing.assert_allclose(out[:36], 0.125)
            self.assertTrue((out[36:] == 0).all())
            self.assertEqual(path.read_bytes(), original)

    def test_device_failure_releases_stream(self):
        player = AudioPreview()
        player.data = np.zeros((100, 1), dtype='float32')
        with patch('afc_lab.audio_preview.sd.OutputStream') as factory:
            factory.return_value.start.side_effect = RuntimeError('No output')
            with self.assertRaises(RuntimeError): player.play()
            factory.return_value.close.assert_called_once()
            self.assertIsNone(player.stream)


if __name__ == '__main__':
    unittest.main()
