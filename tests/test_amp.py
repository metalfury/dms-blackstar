"""Run with: python3 -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['XDG_STATE_HOME'] = tempfile.mkdtemp()
os.environ['XDG_DATA_HOME'] = tempfile.mkdtemp()

from bsamp import amp as A, presets as P  # noqa: E402
from bsamp.fake import FakeTransport, STATE  # noqa: E402


class Protocol(unittest.TestCase):
    def setUp(self):
        self.t = FakeTransport()
        self.amp = A.Amp(self.t)

    def test_decode_real_packet(self):
        s = A.decode(STATE)
        self.assertEqual((s['voice'], s['gain'], s['bass'], s['delay_time']), (4, 126, 97, 512))

    def test_encode_roundtrip(self):
        s = A.decode(STATE)
        s.update(gain=10, delay_time=1234, reverb=1, fx_focus=3, reverb_level=77)
        out = A.encode(s, STATE)
        self.assertEqual(A.decode(out), s)
        self.assertEqual(out[A.FOCUS_LEVEL_BYTE], 77)

    def test_set_packets(self):
        self.amp.set('gain', 64)
        self.amp.set('delay_time', 700)
        self.assertEqual(list(self.t.sent[-2][:5]), [0x03, 0x02, 0x00, 0x01, 64])
        self.assertEqual(list(self.t.sent[-1][:6]), [0x03, 0x1B, 0x00, 0x02, 700 & 0xFF, 700 >> 8])
        with self.assertRaises(A.AmpError):
            self.amp.set('gain', 200)
        with self.assertRaises(A.AmpError):
            self.amp.set('master', 1)

    def test_knob_on_amp_updates_state(self):
        self.amp.refresh()
        seen = []
        self.amp.listeners.append(seen.append)
        self.t.turn('gain', 33)
        self.amp.pump(0.1)
        self.assertEqual(seen[-1]['settings']['gain'], 33)

    def test_write_preset(self):
        doc = P.find('master-of-puppets')
        self.amp.write_preset(4, doc['name'], P.to_settings(doc))
        self.assertEqual(self.amp.name(4), 'MASTER OF PUPPETS')
        got = P.from_settings(self.amp.preset(4))
        for k in ('voice', 'gain', 'middle', 'isf'):
            self.assertEqual(got[k], doc[k])
        self.assertEqual(got['reverb']['on'], False)

    def test_backup_restore(self):
        d = P.backup(self.amp)
        self.amp.write_preset(1, 'XX', {'gain': 1})
        P.restore(self.amp, d)
        self.assertEqual(self.amp.name(1), 'ACOUSTIC LIKE')
        self.assertEqual(self.amp.preset(1)['gain'], 126)

    def test_library_valid(self):
        bank = P.bank()
        self.assertEqual([d['slot'] for d in bank], [1, 2, 3, 4, 5, 6])
        for doc, _path, _u in P.library():
            s = P.to_settings(doc)
            for k, v in s.items():
                _cid, lo, hi = A.CONTROLS[k]
                self.assertTrue(lo <= v <= hi, (doc['name'], k, v))
            self.assertLessEqual(len(A.clean_name(doc['name'])), A.NAME_LEN)

    def test_doc_roundtrip(self):
        s = A.decode(STATE)
        s['fx_focus'] = 2
        s2 = P.to_settings(P.from_settings(s))
        for k, v in s2.items():
            self.assertEqual(s[k], v, k)


if __name__ == '__main__':
    unittest.main()
