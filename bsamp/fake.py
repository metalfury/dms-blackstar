"""A simulated ID:Core V2 for tests and for trying the app without the amp
(BSAMP_FAKE=1). It answers the same packets the real amp does."""

import os
import select

from . import amp as A

# State packet captured from a real ID:Core V2
STATE = bytes.fromhex(
    '0301002a047e7f61292e0b040d477f40'
    '7f01000000000a40323200 0a00320002'.replace(' ', '') +
    '000a0032')
STATE = STATE + bytes(64 - len(STATE))
NAMES = ['ACOUSTIC LIKE', 'BLEACH CLEAN', 'TWO ROCK CRUNCH', 'JAMES MASTER OF P',
         'OVERDRIVE 1', 'TRASH 1']


class FakeTransport:
    product = 0x0011

    def __init__(self):
        self.r, self.w = os.pipe()
        self.state = bytearray(STATE)
        self.presets = {}
        for i in range(1, A.SLOTS + 1):
            p = bytearray(STATE)
            p[0:4] = [0x02, 0x05, i, 0x2A]
            p[4] = i - 1
            self.presets[i] = p
        self.names = {i + 1: n for i, n in enumerate(NAMES)}
        self.pending_name = None
        self.sent = []

    def fileno(self):
        return self.r

    def _reply(self, p):
        os.write(self.w, bytes(p) + bytes(64 - len(p)))

    def _state(self):
        self._reply(self.state)

    def write(self, packet):
        p = bytes(packet) + bytes(64 - len(packet))
        self.sent.append(p)
        if p[0] == 0x81:
            self._reply([0x07, 0, 0, 3, 4, 0, 1, 1, 0x40])
            self._state()
            self._reply([0x08, 0x01, 0, 0x1B, 0])
        elif p[0] == 0x03 and p[3] in (1, 2):
            self.state[p[1] + 3] = p[4]
            if p[3] == 2:
                self.state[p[1] + 4] = p[5]
            self._reply([0x08, 0x03, 0, 1, 1])
        elif p[0] == 0x02 and p[1] == 0x04:
            name = self.names.get(p[2], '').encode()
            pkt = bytearray(64)
            pkt[0:4] = [0x02, 0x04, p[2], 0x15]
            pkt[4:25] = (name + b'\xff' * 21)[:21] if name else b'\xff' * 21
            self._reply(pkt)
        elif p[0] == 0x02 and p[1] == 0x05:
            self._reply(self.presets[p[2]])
        elif p[0] == 0x02 and p[1] == 0x01:
            pr = self.presets[p[2]]
            self.state[4:46] = pr[4:46]
            self._reply([0x02, 0x06, p[2], 0])
            self._state()
        elif p[0] == 0x02 and p[1] == 0x02:
            self.pending_name = bytes(b for b in p[4:25] if b).decode()
        elif p[0] == 0x02 and p[1] == 0x03:
            pr = bytearray(p)
            pr[0:4] = [0x02, 0x05, p[2], 0x2A]
            self.presets[p[2]] = pr
            if self.pending_name is not None:
                self.names[p[2]] = self.pending_name
                self.pending_name = None

    def turn(self, control, value):
        """Simulate turning a knob on the amp."""
        cid = A.CONTROLS[control][0]
        self.state[cid + 3] = value
        self._state()

    def read(self, timeout):
        r, _, _ = select.select([self.r], [], [], timeout)
        if not r:
            return None
        return os.read(self.r, 64)

    def close(self):
        os.close(self.r)
        os.close(self.w)
