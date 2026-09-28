import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
import numpy as np
from referencia.session_audit import audit_data, read_float_wav
from referencia.storage import ROOT, digest, read_json, write_json


class SessionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pointer=ROOT / "build/session_capture_tests/latest.txt"
        if not pointer.exists():
            raise RuntimeError("Run CTest SessionCaptureTest first")
        cls.run_directory=Path(pointer.read_text().strip())
        cls.summary=read_json(cls.run_directory / "summary.json")

    def test_exported_sessions_and_expected_failures(self):
        results=[]
        for path in self.summary["sessions"]:
            result=audit_data(path)
            self.assertEqual(result["passed"],read_json(Path(path)/"manifest.json")["complete"],path)
            results.append({"path":path,**result})
        self.assertGreaterEqual(sum(r["passed"] for r in results),10)
        self.assertEqual(sum(not r["passed"] for r in results),2)
        write_json(self.run_directory / "python_audits.json",results)

    def test_wav_segment_roundtrip(self):
        session=Path(self.summary["sessions"][0])
        manifest=read_json(session/"manifest.json")
        self.assertGreater(len(manifest["segments"]),1)
        chunks=[]
        for segment in manifest["segments"]:
            rate,data=read_float_wav(session/segment["file"])
            self.assertEqual(rate,16000)
            chunks.append(data)
        audio=np.concatenate(chunks)
        # During a normal, non-limited bypass/cancellation sample the export uses
        # the exact float32 gain and clean value already computed by the processor.
        events=[json.loads(s) for s in (session/"events.jsonl").read_text().splitlines()]
        verified=0
        for i,e in enumerate(events):
            end=events[i+1]["sample"] if i+1<len(events) else len(audio)
            if e["clean_valid"] and not e["muted"] and not e["noise"] and not e["limited"]:
                part=audio[e["sample"]:end]
                np.testing.assert_array_equal((part[:,3]*part[:,6]).view(np.uint32),part[:,4].view(np.uint32))
                verified+=len(part)
        self.assertGreater(verified,0)

    def test_corruption_and_missing_metadata_never_pass(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
            dest=Path(tmp)/"session"; shutil.copytree(self.summary["sessions"][1],dest)
            wav=next(dest.glob("audio_*.wav"))
            raw=bytearray(wav.read_bytes()); raw[-1]^=1; wav.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,"Hash mismatch"):
                audit_data(dest)

    def test_wav_rejects_truncation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
            file=Path(tmp)/"truncated.wav"; file.write_bytes(b"RIFF"+struct.pack("<I",80)+b"WAVE")
            with self.assertRaises(ValueError): read_float_wav(file)


if __name__ == "__main__": unittest.main()
