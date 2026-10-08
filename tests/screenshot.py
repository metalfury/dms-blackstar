"""Render the app with the simulated amp and save PNGs (needs a display, e.g. xvfb-run)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['BSAMP_FAKE'] = '1'
from bsamp import gui  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else 'shot'
w, h = (int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else '1000x760').split('x'))
steps = sys.argv[3].split(',') if len(sys.argv) > 3 else []
app = gui.App()


def snap(name):
    win = app.win
    paintable = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, win.get_width(), win.get_height())
    node = snap.to_node()
    tex = win.get_renderer().render_texture(node, None)
    tex.save_to_png(name)
    print('saved', name)


def run_steps():
    win = app.win
    for st in steps:
        if st == 'preview':
            row = win.lib_list.get_row_at_index(4)
            win.on_library_activated(None, row)
        elif st.startswith('slot'):
            win.on_slot_activated(None, win.slot_rows[int(st[4:]) - 1])
        elif st == 'offline':
            win.disconnect_amp()
    GLib.timeout_add(700, lambda: (snap(out + '.png'), app.quit()))
    return False


def activate(_a):
    def later():
        app.win.set_default_size(w, h)
        GLib.timeout_add(1200, run_steps)
    GLib.idle_add(later)


app.connect('activate', activate)
app.run([])
