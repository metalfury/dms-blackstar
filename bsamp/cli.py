"""bsamp - control a Blackstar ID:Core from the command line."""

import argparse
import json
import os
import sys

from . import amp as A
from . import presets as P

HELP = """\
commands:
  status [--json]              current settings
  slots [--json]               patch names in the 6 slots
  select <slot>                switch to a patch
  show <slot> [--json]         settings stored in a slot
  set <control> <value>        change a control live (see `bsamp controls`)
  controls                     list controls and their ranges
  load <patch>                 apply a library patch live, without saving it
  write <slot> <patch>         store a library patch (file, name or slug) in a slot
  bank                         store the whole bank (library patches with a slot)
  save <slot> [name]           store the current sound in a slot
  rename <slot> <name>         rename a slot
  export <slot> [file]         save a slot as a patch file in your library
  library [--json]             list library patches
  backup                       dump all slots to ~/.local/share/bsamp/backups
  restore [dir]                write a backup back (default: the newest)
  watch                        print events as JSON lines (for the bar widget)
  gui                          open the app
"""


def open_amp():
    if os.environ.get('BSAMP_FAKE'):
        from .fake import FakeTransport
        return A.Amp(FakeTransport())
    try:
        return A.Amp()
    except A.AmpError as e:
        sys.exit(f'bsamp: {e}')


def open_amp_quiet():
    if os.environ.get('BSAMP_FAKE'):
        from .fake import FakeTransport
        return A.Amp(FakeTransport())
    return A.Amp()


def parse_value(control, value):
    if control in A.ENUMS:
        try:
            return P._enum(int(value) if value.isdigit() else value,
                           A.ENUMS[control], control)
        except ValueError as e:
            sys.exit(f'bsamp: {e}')
    if value.lower() in ('on', 'true', 'yes'):
        return 1
    if value.lower() in ('off', 'false', 'no'):
        return 0
    return int(value)


def print_settings(s):
    doc = P.from_settings(s)
    print(f"voice   {doc['voice']}")
    print('amp     ' + '  '.join(f'{k} {s[k]}' for k in P.AMP_KEYS))
    for fx in ('mod', 'delay', 'reverb'):
        d = doc[fx]
        rest = '  '.join(f'{k} {v}' for k, v in d.items() if k not in ('on', 'type'))
        print(f"{fx:<7} {'on ' if d['on'] else 'off'} {d['type']:<9} {rest}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog='bsamp', description=__doc__, epilog=HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', nargs='?', default='status')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--json', action='store_true')
    o = ap.parse_args(argv)
    a = o.args

    if o.cmd == 'gui':
        from . import gui
        return gui.main()
    if o.cmd == 'controls':
        for k, (cid, lo, hi) in A.CONTROLS.items():
            extra = ' (' + ', '.join(A.ENUMS[k]) + ')' if k in A.ENUMS else ''
            ro = '  [read only]' if k in A.READ_ONLY else ''
            print(f'{k:<15} {lo}..{hi}{extra}{ro}')
        return
    if o.cmd == 'library':
        lib = P.library()
        if o.json:
            print(json.dumps([dict(d, path=p, user=u) for d, p, u in lib]))
        for d, p, u in lib:
            slot = f"[{d['slot']}] " if 'slot' in d else '    '
            print(f"{slot}{d['name']:<21} {d['voice']:<13} {'(yours)' if u else ''}")
        return

    if o.cmd == 'status' and o.json:
        try:
            amp = open_amp_quiet()
        except A.AmpError as e:
            print(json.dumps({'connected': False, 'error': str(e)}))
            return
        s = amp.refresh()
        print(json.dumps({'connected': True, 'model': amp.model, 'slot': amp.slot,
                          'names': amp.names(), 'settings': s,
                          'voice': A.VOICES[s['voice']] if s['voice'] < 6 else ''}))
        return

    amp = open_amp()

    if o.cmd == 'status':
        s = amp.refresh()
        print(amp.model + (f'  slot {amp.slot}' if amp.slot else ''))
        print_settings(s)
    elif o.cmd == 'slots':
        names = amp.names()
        if o.json:
            print(json.dumps(names))
        for i, n in enumerate(names, 1):
            print(f'{i}  {n or "(empty)"}')
    elif o.cmd == 'select':
        amp.select(int(a[0]))
    elif o.cmd == 'show':
        s = amp.preset(int(a[0]))
        if o.json:
            print(json.dumps(P.from_settings(s, amp.name(int(a[0])), int(a[0]))))
        else:
            print(f'{a[0]}  {amp.name(int(a[0]))}')
            print_settings(s)
    elif o.cmd == 'set':
        amp.set(a[0], parse_value(a[0], a[1]))
    elif o.cmd == 'load':
        amp.apply(P.to_settings(P.find(a[0])))
    elif o.cmd == 'write':
        slot, doc = int(a[0]), P.find(a[1])
        b = P.ensure_daily_backup(amp)
        if b:
            print(f'backup: {b}')
        amp.write_preset(slot, doc['name'], P.to_settings(doc))
        amp.select(slot)
        print(f"{slot}  {A.clean_name(doc['name'])}")
    elif o.cmd == 'bank':
        b = P.ensure_daily_backup(amp)
        if b:
            print(f'backup: {b}')
        for doc in P.bank():
            amp.write_preset(doc['slot'], doc['name'], P.to_settings(doc))
            print(f"{doc['slot']}  {A.clean_name(doc['name'])}")
    elif o.cmd == 'save':
        slot = int(a[0])
        name = ' '.join(a[1:]) or amp.name(slot) or f'PATCH {slot}'
        b = P.ensure_daily_backup(amp)
        if b:
            print(f'backup: {b}')
        amp.write_preset(slot, name, amp.refresh())
        print(f'{slot}  {A.clean_name(name)}')
    elif o.cmd == 'rename':
        slot = int(a[0])
        P.ensure_daily_backup(amp)
        amp.write_preset(slot, ' '.join(a[1:]))
    elif o.cmd == 'export':
        slot = int(a[0])
        name = amp.name(slot) or f'PATCH {slot}'
        doc = P.from_settings(amp.preset(slot), name)
        path = a[1] if len(a) > 1 else os.path.join(P.USER, P.slug(name) + '.json')
        P.save(doc, path)
        print(path)
    elif o.cmd == 'backup':
        print(P.backup(amp))
    elif o.cmd == 'restore':
        d = a[0] if a else (P.backups() or [None])[0]
        if not d:
            sys.exit('bsamp: no backups')
        P.restore(amp, d)
        print(f'restored {d}')
    elif o.cmd == 'watch':
        watch(amp)
    else:
        ap.print_help()
        return 2


def watch(amp):
    """JSON lines: one 'hello' with everything, then events."""
    out = sys.stdout

    def emit(obj):
        out.write(json.dumps(obj) + '\n')
        out.flush()

    s = amp.refresh()
    emit({'type': 'hello', 'model': amp.model, 'names': amp.names(),
          'slot': amp.slot, 'settings': s})
    amp.listeners.append(emit)
    while True:
        amp.pump(5.0)


def run():
    try:
        sys.exit(main())
    except A.AmpError as e:
        sys.exit(f'bsamp: {e}')
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    except OSError as e:     # amp unplugged while running
        sys.exit(f'bsamp: {e}')
