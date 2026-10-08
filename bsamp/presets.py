"""Patch files: a readable JSON form of the amp's settings.

    {
      "name": "MASTER OF PUPPETS",
      "slot": 4,
      "notes": "...",
      "voice": "Super Crunch",
      "gain": 98, "volume": 70, "bass": 82, "middle": 38, "treble": 86, "isf": 22,
      "mod":    {"on": false, "type": "Chorus", "level": 40, "speed": 30, "segval": 12, "manual": 64},
      "delay":  {"on": false, "type": "Analogue", "time": 400, "feedback": 8, "level": 30},
      "reverb": {"on": true, "type": "Room", "size": 10, "level": 18},
      "focus": "reverb"
    }

Knob values are 0..127 like on the wire (the app shows them as 0..10).
"""

import datetime
import json
import os

from . import amp as A

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.join(os.path.dirname(HERE), 'presets')
CONFIG = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'bsamp')
USER = os.path.join(CONFIG, 'presets')
BACKUPS = os.path.join(os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share')),
                       'bsamp', 'backups')

FX = {
    'mod': {'type': ('mod_type', A.MOD_TYPES), 'level': 'mod_level', 'speed': 'mod_speed',
            'segval': 'mod_segval', 'manual': 'mod_manual'},
    'delay': {'type': ('delay_type', A.DELAY_TYPES), 'time': 'delay_time',
              'feedback': 'delay_feedback', 'level': 'delay_level'},
    'reverb': {'type': ('reverb_type', A.REVERB_TYPES), 'size': 'reverb_size',
               'level': 'reverb_level'},
}
FOCUS = ['', 'mod', 'delay', 'reverb']
AMP_KEYS = ['gain', 'volume', 'bass', 'middle', 'treble', 'isf']


def _enum(value, names, field):
    if isinstance(value, int):
        return value
    for i, n in enumerate(names):
        if n.lower().replace(' ', '') == str(value).lower().replace(' ', ''):
            return i
    raise ValueError(f'{field}: unknown value {value!r} (one of {", ".join(names)})')


def to_settings(doc):
    """Patch document -> flat settings dict for the amp."""
    s = {}
    if 'voice' in doc:
        s['voice'] = _enum(doc['voice'], A.VOICES, 'voice')
    for k in AMP_KEYS:
        if k in doc:
            s[k] = int(doc[k])
    for fx, fields in FX.items():
        d = doc.get(fx)
        if not d:
            continue
        if 'on' in d:
            s[fx] = 1 if d['on'] else 0
        for key, target in fields.items():
            if key not in d:
                continue
            if isinstance(target, tuple):
                s[target[0]] = _enum(d[key], target[1], f'{fx}.type')
            else:
                s[target] = int(d[key])
    focus = doc.get('focus')
    if focus is None:   # focus the last enabled effect, like the panel does
        on = [f for f in ('mod', 'delay', 'reverb') if s.get(f)]
        focus = on[-1] if on else ''
    s['fx_focus'] = FOCUS.index(focus) if focus in FOCUS else int(focus)
    return s


def from_settings(s, name='', slot=None, notes=''):
    """Flat settings -> patch document."""
    doc = {'name': name}
    if slot:
        doc['slot'] = slot
    if notes:
        doc['notes'] = notes
    doc['voice'] = A.VOICES[s['voice']] if s['voice'] < len(A.VOICES) else s['voice']
    for k in AMP_KEYS:
        doc[k] = s[k]
    for fx, fields in FX.items():
        d = {'on': bool(s[fx])}
        for key, target in fields.items():
            if isinstance(target, tuple):
                v = s[target[0]]
                d[key] = target[1][v] if v < len(target[1]) else v
            else:
                d[key] = s[target]
        doc[fx] = d
    doc['focus'] = FOCUS[s['fx_focus']] if s['fx_focus'] < 4 else s['fx_focus']
    return doc


def load(path):
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    doc.setdefault('name', os.path.splitext(os.path.basename(path))[0])
    to_settings(doc)        # validate early
    return doc


def save(doc, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write('\n')


def slug(name):
    out = ''.join(c.lower() if c.isalnum() else '-' for c in name).strip('-')
    while '--' in out:
        out = out.replace('--', '-')
    return out or 'patch'


def library():
    """All patch files: bundled first, then the user's own (which win on
    a name clash). Returns a list of (doc, path, is_user)."""
    seen = {}
    for d, user in ((BUNDLED, False), (USER, True)):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.json'):
                continue
            path = os.path.join(d, fn)
            try:
                doc = load(path)
            except (ValueError, OSError) as e:
                print(f'warning: {path}: {e}')
                continue
            seen[doc['name'].upper()] = (doc, path, user)
    return sorted(seen.values(), key=lambda e: (e[0].get('slot', 99), e[0]['name']))


def find(ref):
    """Find a patch by file path, slug or (case-insensitive) name."""
    if os.path.isfile(ref):
        return load(ref)
    for doc, path, _ in library():
        if ref.upper() in (doc['name'].upper(), slug(doc['name']).upper(),
                           os.path.splitext(os.path.basename(path))[0].upper()):
            return doc
    raise ValueError(f'no patch called {ref!r}')


# -- backups -----------------------------------------------------------

def backup(amp, reason='manual'):
    """Dump every slot (name, raw packet and readable form)."""
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    d = os.path.join(BACKUPS, f'{stamp}-{reason}')
    os.makedirs(d, exist_ok=True)
    for slot in range(1, A.SLOTS + 1):
        raw = amp.preset_raw(slot)
        name = amp.name(slot)
        doc = from_settings(A.decode(raw), name, slot)
        doc['raw'] = raw.hex()
        save(doc, os.path.join(d, f'{slot}-{slug(name or "empty")}.json'))
    return d


def backups():
    if not os.path.isdir(BACKUPS):
        return []
    return sorted((os.path.join(BACKUPS, d) for d in os.listdir(BACKUPS)), reverse=True)


def restore(amp, d):
    for fn in sorted(os.listdir(d)):
        if fn.endswith('.json'):
            doc = load(os.path.join(d, fn))
            amp.write_preset(doc['slot'], doc['name'], raw=bytes.fromhex(doc['raw']))


def ensure_daily_backup(amp):
    """Take a backup before the first write of the day."""
    today = datetime.datetime.now().strftime('%Y%m%d')
    if not any(os.path.basename(b).startswith(today) for b in backups()):
        return backup(amp, 'auto')
    return None


def bank():
    """Library patches that name a slot, one per slot (yours win)."""
    out = {}
    for doc, path, user in library():
        slot = doc.get('slot')
        if slot and (slot not in out or user):
            out[slot] = doc
    return [out[k] for k in sorted(out)]
