"""Talk to a Blackstar ID:Core amplifier over its USB HID control interface.

The amp exposes a vendor HID interface next to its USB audio interfaces.
We use the kernel's hidraw node, so the audio side stays bound to
snd-usb-audio and the amp keeps working as a sound card.

The protocol was worked out by the Outsider project
(https://github.com/jonathanunderwood/outsider) for the original ID
amps; the ID:Core V2 speaks the same protocol.

Packets are 64 bytes. A full settings block is 42 bytes and starts at
byte 4; the value of control id N sits at byte N + 3 of a packet.
"""

import glob
import os
import select
import time

VENDOR = 0x27D4
MODELS = {0x0001: 'ID:TVP', 0x0010: 'ID:Core', 0x0011: 'ID:Core V2'}
SLOTS = 6                    # the Core stores one patch per voice position
NAME_LEN = 20

VOICES = ['Clean Warm', 'Clean Bright', 'Crunch', 'Super Crunch', 'OD1', 'OD2']
MOD_TYPES = ['Phaser', 'Flanger', 'Chorus', 'Tremolo']
DELAY_TYPES = ['Linear', 'Analogue', 'Tape', 'Multi']
REVERB_TYPES = ['Room', 'Hall', 'Spring', 'Plate']

# name: (control id, min, max)
CONTROLS = {
    'voice': (0x01, 0, 5),
    'gain': (0x02, 0, 127),
    'volume': (0x03, 0, 127),
    'bass': (0x04, 0, 127),
    'middle': (0x05, 0, 127),
    'treble': (0x06, 0, 127),
    'isf': (0x07, 0, 127),
    'tvp_valve': (0x08, 0, 5),
    'resonance': (0x0B, 0, 127),
    'presence': (0x0C, 0, 127),
    'master': (0x0D, 0, 127),
    'tvp': (0x0E, 0, 1),
    'mod': (0x0F, 0, 1),
    'delay': (0x10, 0, 1),
    'reverb': (0x11, 0, 1),
    'mod_type': (0x12, 0, 3),
    'mod_segval': (0x13, 0, 31),
    'mod_manual': (0x14, 0, 127),
    'mod_level': (0x15, 0, 127),
    'mod_speed': (0x16, 0, 127),
    'delay_type': (0x17, 0, 3),
    'delay_feedback': (0x18, 0, 31),
    'delay_level': (0x1A, 0, 127),
    'delay_time': (0x1B, 100, 2000),     # ms, two bytes little endian
    'reverb_type': (0x1D, 0, 3),
    'reverb_size': (0x1E, 0, 31),
    'reverb_level': (0x20, 0, 127),
    'fx_focus': (0x24, 0, 3),     # 0 = no effect has focus
}
# Controls the front panel of the Core does not have; we read them but
# never send them.
READ_ONLY = {'resonance', 'presence', 'master', 'tvp', 'tvp_valve'}
# The panel's shared "level" knob mirrors the level of the focused effect
# at byte 12; the amp keeps it in sync itself.
FOCUS_LEVEL_BYTE = 12
FOCUS_LEVEL = {1: 'mod_level', 2: 'delay_level', 3: 'reverb_level'}

STATE_FILE = os.path.join(os.environ.get('XDG_STATE_HOME', os.path.expanduser('~/.local/state')),
                          'bsamp', 'slot')

ENUMS = {'voice': VOICES, 'mod_type': MOD_TYPES,
         'delay_type': DELAY_TYPES, 'reverb_type': REVERB_TYPES}


class AmpError(Exception):
    pass


class NotFound(AmpError):
    pass


# --------------------------------------------------------------------------
# Settings block <-> dict

def decode(block):
    """Decode a 64-byte settings packet (state or preset) into a dict."""
    s = {}
    for name, (cid, lo, hi) in CONTROLS.items():
        if name == 'delay_time':
            s[name] = block[cid + 3] | (block[cid + 4] << 8)
        else:
            s[name] = block[cid + 3]
    return s


def encode(settings, base):
    """Write the values in ``settings`` into a copy of the 64-byte ``base``
    packet. Bytes we know nothing about are kept."""
    out = bytearray(base)
    for name, value in settings.items():
        if name not in CONTROLS:
            continue
        cid, lo, hi = CONTROLS[name]
        value = max(lo, min(hi, int(value)))
        if name == 'delay_time':
            out[cid + 3] = value & 0xFF
            out[cid + 4] = value >> 8
        else:
            out[cid + 3] = value
    focus = settings.get('fx_focus', out[CONTROLS['fx_focus'][0] + 3])
    if focus in FOCUS_LEVEL:
        out[FOCUS_LEVEL_BYTE] = out[CONTROLS[FOCUS_LEVEL[focus]][0] + 3]
    return bytes(out)


def decode_name(packet):
    raw = bytes(b for b in packet[4:4 + 21] if b not in (0x00, 0xFF))
    name = raw.decode('ascii', 'replace')
    if not name or any(not (32 <= ord(c) < 127) for c in name):
        return ''
    return name.strip()


def clean_name(name):
    name = ''.join(c for c in name.upper() if 32 <= ord(c) < 127)
    return name[:NAME_LEN].strip()


# --------------------------------------------------------------------------
# Transport

def find_hidraw():
    """Return (device node, product id) of the connected amp."""
    found = []
    for uevent in sorted(glob.glob('/sys/class/hidraw/hidraw*/device/uevent')):
        try:
            with open(uevent) as f:
                text = f.read()
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith('HID_ID='):
                _, vid, pid = line[7:].split(':')
                if int(vid, 16) == VENDOR and int(pid, 16) in MODELS:
                    found.append(('/dev/' + uevent.split('/')[4], int(pid, 16)))
    if not found:
        raise NotFound('no Blackstar ID amplifier found')
    return found[0]


class Hidraw:
    def __init__(self, path=None):
        if path is None:
            path, self.product = find_hidraw()
        else:
            self.product = 0x0011
        self.path = path
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise AmpError(f'no permission for {path} - install the udev rule')

    def fileno(self):
        return self.fd

    def write(self, packet):
        packet = bytes(packet) + bytes(64 - len(packet))
        os.write(self.fd, b'\0' + packet)   # report id 0

    def read(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        try:
            return os.read(self.fd, 64)
        except BlockingIOError:
            return None

    def close(self):
        os.close(self.fd)


# --------------------------------------------------------------------------
# Amp

class Amp:
    """High level access to the amp. ``transport`` defaults to the hidraw
    node of the first connected amp."""

    def __init__(self, transport=None):
        self.t = transport or Hidraw()
        self.model = MODELS.get(getattr(self.t, 'product', 0x11), 'ID amp')
        self.state = None          # last full settings packet (bytes)
        self.slot = self._load_slot()   # last patch selected through us
        self.listeners = []

    def fileno(self):
        return self.t.fileno()

    @staticmethod
    def _load_slot():
        try:
            with open(STATE_FILE) as f:
                v = int(f.read().strip() or 0)
            return v if 1 <= v <= SLOTS else None
        except (OSError, ValueError):
            return None

    def _save_slot(self, slot):
        self.slot = slot
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                f.write(f'{slot or 0}\n')
        except OSError:
            pass

    def close(self):
        self.t.close()

    # -- low level -----------------------------------------------------
    def send(self, packet):
        self.t.write(packet)

    def handle(self, p):
        """Process one incoming packet; returns an event dict or None."""
        if len(p) < 4:
            return None
        ev = None
        if p[0] == 0x03 and p[3] == 0x2A:
            self.state = bytes(p)
            ev = {'type': 'state', 'settings': decode(p)}
        elif p[0] == 0x03 and p[3] in (0x01, 0x02):
            # Single control change (original ID amps)
            if self.state is not None:
                st = bytearray(self.state)
                st[p[1] + 3] = p[4]
                if p[3] == 0x02:
                    st[p[1] + 4] = p[5]
                self.state = bytes(st)
                ev = {'type': 'state', 'settings': decode(self.state)}
        elif p[0] == 0x02 and p[1] == 0x06:
            self._save_slot(p[2])
            ev = {'type': 'slot', 'slot': p[2]}
        elif p[0] == 0x08 and p[1] == 0x03:
            if p[4] == 1:
                self.slot = None
            ev = {'type': 'manual', 'manual': bool(p[4])}
        elif p[0] == 0x08 and p[1] == 0x11:
            ev = {'type': 'tuner', 'on': bool(p[4])}
        elif p[0] == 0x09:
            note = ['', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B', 'C', 'C#', 'D', 'D#']
            ev = {'type': 'tune', 'note': note[p[1]] if p[1] < 13 else '',
                  'cents': p[2] - 50}
        elif p[0] == 0x08:
            # Third reply to the startup packet; byte 4 looks like the
            # selected patch (0 = manual)
            pass
        for cb in self.listeners:
            if ev:
                cb(ev)
        return ev

    def pump(self, timeout=0.0):
        """Read and handle every packet that is waiting."""
        evs = []
        while True:
            p = self.t.read(timeout)
            if p is None:
                return evs
            ev = self.handle(p)
            if ev:
                evs.append(ev)
            timeout = 0.0

    def request(self, packet, match, timeout=1.0):
        """Send ``packet`` and return the first reply for which ``match``
        is true. Other packets are still handled."""
        self.send(packet)
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise AmpError('no reply from the amplifier')
            p = self.t.read(left)
            if p is None:
                continue
            self.handle(p)
            if match(p):
                return bytes(p)

    # -- queries -------------------------------------------------------
    def refresh(self):
        """Ask for the current settings."""
        self.request([0x81, 0, 0, 0x04, 0x03, 0x06, 0x02, 0x7A],
                     lambda p: p[0] == 0x03 and p[3] == 0x2A)
        self.pump(0.15)
        return decode(self.state)

    def settings(self):
        if self.state is None:
            return self.refresh()
        return decode(self.state)

    def name(self, slot):
        p = self.request([0x02, 0x04, slot, 0x00],
                         lambda p: p[0] == 0x02 and p[1] == 0x04 and p[2] == slot)
        return decode_name(p)

    def names(self):
        return [self.name(i) for i in range(1, SLOTS + 1)]

    def preset_raw(self, slot):
        return self.request([0x02, 0x05, slot, 0x00],
                            lambda p: p[0] == 0x02 and p[1] == 0x05 and p[2] == slot)

    def preset(self, slot):
        return decode(self.preset_raw(slot))

    # -- changes -------------------------------------------------------
    def set(self, name, value):
        if name not in CONTROLS:
            raise AmpError(f'unknown control {name}')
        if name in READ_ONLY:
            raise AmpError(f'{name} cannot be set on this amp')
        cid, lo, hi = CONTROLS[name]
        value = int(value)
        if not lo <= value <= hi:
            raise AmpError(f'{name} must be {lo}..{hi}')
        if name == 'delay_time':
            pkt = [0x03, cid, 0x00, 0x02, value & 0xFF, value >> 8]
        else:
            pkt = [0x03, cid, 0x00, 0x01, value]
        self.send(pkt)
        if self.state is not None:          # keep our copy current
            st = bytearray(self.state)
            st[cid + 3] = pkt[4]
            if len(pkt) > 5:
                st[cid + 4] = pkt[5]
            self.state = bytes(st)

    def apply(self, settings):
        """Set every writable control in ``settings`` (live, not saved)."""
        order = ['voice'] + [k for k in settings if k not in ('voice', 'fx_focus')]
        if settings.get('fx_focus'):
            order.append('fx_focus')
        for k in order:
            if k in settings and k in CONTROLS and k not in READ_ONLY:
                self.set(k, settings[k])
                time.sleep(0.004)

    def select(self, slot):
        if not 1 <= slot <= SLOTS:
            raise AmpError(f'slot must be 1..{SLOTS}')
        self.send([0x02, 0x01, slot, 0x00])
        self._save_slot(slot)

    def write_preset(self, slot, name, settings=None, raw=None):
        """Store a patch. ``raw`` is a full 64-byte preset packet (from a
        backup); otherwise ``settings`` are merged into what the slot
        holds now."""
        if not 1 <= slot <= SLOTS:
            raise AmpError(f'slot must be 1..{SLOTS}')
        base = bytes(raw) if raw is not None else self.preset_raw(slot)
        block = encode(settings or {}, base)
        namepkt = bytearray(64)
        namepkt[0:4] = [0x02, 0x02, slot, 0x15]
        n = clean_name(name).encode('ascii')
        namepkt[4:4 + len(n)] = n
        setpkt = bytearray(block)
        setpkt[0:4] = [0x02, 0x03, slot, 0x29]
        self.send(namepkt)
        time.sleep(0.02)
        self.send(setpkt)
        self.pump(0.3)
        # Read back to confirm
        got, want = decode(self.preset_raw(slot)), decode(setpkt)
        bad = [k for k in want if k not in READ_ONLY and got[k] != want[k]]
        if bad:
            raise AmpError(f'slot {slot} did not take: ' + ', '.join(bad))
        if self.name(slot) != clean_name(name):
            raise AmpError(f'slot {slot} did not take the new name')
