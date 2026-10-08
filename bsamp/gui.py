"""Blackstar Amp - an amp-faceplate style editor for the ID:Core (GTK 4)."""

import ctypes
import os
import sys
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import amp as A  # noqa: E402
from . import presets as P  # noqa: E402
from .widgets import KnobControl, VoiceSelector, led, revert_button, set_led, set_revert  # noqa: E402

APP_ID = 'io.github.metalfury.bsamp'
FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'fonts')
VOICE_SHORT = ['WARM', 'BRIGHT', 'CRUNCH', 'SUPER', 'OD1', 'OD2']
FX = [('mod', 'Mod', 'Modulation', 'mod_type', A.MOD_TYPES),
      ('delay', 'Delay', 'Delay', 'delay_type', A.DELAY_TYPES),
      ('reverb', 'Reverb', 'Reverb', 'reverb_type', A.REVERB_TYPES)]
FX_KNOBS = {
    'mod': [('mod_level', 'Level', 'knob'), ('mod_speed', 'Speed', 'knob'),
            ('mod_segval', 'Amount', 'seg'), ('mod_manual', 'Manual', 'knob')],
    'delay': [('delay_time', 'Time', 'ms'), ('delay_feedback', 'Feedback', 'seg'),
              ('delay_level', 'Level', 'knob')],
    'reverb': [('reverb_size', 'Size', 'seg'), ('reverb_level', 'Level', 'knob')],
}

CSS = """
window.amp, window.amp .amp-bg {
  background-color: #121213;
  background-image: radial-gradient(circle, rgba(255,255,255,.045) 1px, transparent 1.4px),
                    radial-gradient(circle, rgba(0,0,0,.55) 1px, transparent 1.4px);
  background-size: 5px 5px, 7px 7px;
  background-position: 0 0, 2px 3px;
  color: #ece6da;
}
.amp headerbar {
  background: rgba(10,10,11,.85); box-shadow: none;
  border-bottom: 1px solid rgba(255,255,255,.06); color: #ece6da;
}
.amp .title-main { font-family: "Barlow Condensed"; font-weight: 700; font-size: 19px; letter-spacing: 2px; }
.amp .title-sub { font-family: Barlow; font-size: 12px; color: #a59c8a; }
.amp .conn { font-family: Barlow; font-size: 13px; color: #a59c8a; }

.plate {
  border-radius: 16px; border: 1px solid #000;
  background-image: repeating-linear-gradient(90deg, rgba(255,255,255,.014) 0, rgba(255,255,255,.014) 1px, transparent 1px, transparent 3px),
                    linear-gradient(180deg, #2c2c2f 0%, #1d1d20 55%, #18181a 100%);
  box-shadow: inset 0 0 0 2px #0c0c0d, inset 0 0 0 3px rgba(231,168,62,.38),
              inset 0 1px 0 4px rgba(255,255,255,.04), 0 24px 48px rgba(0,0,0,.6);
}
.plate-section { padding: 0 14px; border-right: 1px solid rgba(0,0,0,.6); box-shadow: 1px 0 0 rgba(255,255,255,.05); }
.plate-section.last { border-right: none; box-shadow: none; }
.plate flowboxchild { padding: 0; background: none; }
.section-title { font-family: "Barlow Condensed"; font-weight: 600; font-size: 11px; letter-spacing: 3px; color: #a59c8a; }
.knob-name { font-family: "Barlow Condensed"; font-weight: 600; font-size: 14px; letter-spacing: 2px; color: #ece6da;
             text-shadow: 0 1px 0 rgba(0,0,0,.8); }
.knob-value { font-family: Barlow; font-size: 12px; color: #a59c8a; font-feature-settings: "tnum"; }
button.knob-value-btn { min-height: 24px; min-width: 36px; padding: 0 5px; border-radius: 6px; background: none;
                           border: 1px solid transparent; box-shadow: none; color: #a59c8a;
                           font-family: Barlow; font-size: 12px; font-feature-settings: "tnum"; }
button.knob-value-btn:hover { border-color: #3a372f; background: rgba(255,255,255,.04); color: #ece6da; }
button.knob-value-btn:active { border-color: #e7a83e; color: #ffcf73; }
.knob-end { font-family: "Barlow Condensed"; font-weight: 600; font-size: 10px; color: #8f8879; }
.small .knob-name { font-size: 12px; }
.knob-control.dirty .knob-name, .voice-name.dirty { color: #ffcf73; }
.knob-control.dirty button.knob-value-btn { color: #ffcf73; }
button.revert { min-width: 22px; min-height: 22px; padding: 0; border-radius: 99px; background: none;
                border: none; box-shadow: none; color: #e7a83e; font-size: 15px; font-weight: bold; }
button.revert:hover { background: rgba(231,168,62,.15); }
button.fx.dirty { border-color: rgba(255,207,115,.45); }

.led { min-width: 9px; min-height: 9px; border-radius: 99px; background: #3a2a12;
       box-shadow: inset 0 1px 1px rgba(0,0,0,.6); }
.led.on { background: #ffbf4d; box-shadow: 0 0 6px 2px rgba(255,170,40,.65), 0 0 18px rgba(255,170,40,.35); }
.led.green.on { background: #7dffa8; box-shadow: 0 0 6px 2px rgba(80,230,130,.55); }

button.fx { min-width: 100px; min-height: 44px; padding: 0 12px; border-radius: 8px; border: 1px solid #050505;
            background-image: linear-gradient(180deg, #303033, #1f1f22);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 3px 6px rgba(0,0,0,.5);
            color: #ece6da; font-family: "Barlow Condensed"; font-weight: 600; font-size: 14px; letter-spacing: 3px; }
button.fx:hover { background-image: linear-gradient(180deg, #38383b, #252528); }
button.fx.focus { border-color: rgba(231,168,62,.75); }

button.tile { padding: 14px 14px 12px; border-radius: 10px; border: 1px solid #2b2925;
              background-image: linear-gradient(180deg, #1d1c1a, #151514); color: #ece6da; box-shadow: none; }
button.tile:hover { border-color: #4a4335; }
button.tile.on { border-color: #e7a83e; background-image: linear-gradient(180deg, #2b2417, #1a1712);
                 box-shadow: 0 0 0 1px rgba(231,168,62,.35), 0 8px 24px rgba(231,140,30,.12); }
.tile-num { font-family: "Barlow Condensed"; font-weight: 700; font-size: 22px; color: #6f6a60; }
.tile.on .tile-num { color: #ffcf73; }
.tile-name { font-family: "Barlow Condensed"; font-weight: 600; font-size: 15px; letter-spacing: 1.5px; }
.tile-voice, .hint { font-family: Barlow; font-size: 12px; color: #8f8879; }

.seg { border-radius: 8px; border: 1px solid #050505; background: #141416; }
.seg button:first-child { border-top-left-radius: 7px; border-bottom-left-radius: 7px; }
.seg button:last-child { border-top-right-radius: 7px; border-bottom-right-radius: 7px; }
.seg button { min-height: 34px; padding: 0 10px; border-radius: 0; border: none; border-right: 1px solid #050505;
              background: none; box-shadow: none; color: #a59c8a;
              font-family: "Barlow Condensed"; font-weight: 600; font-size: 12px; letter-spacing: 2px; }
.seg button:last-child { border-right: none; }
.seg button:checked { background-image: linear-gradient(180deg, #3a301d, #2a2215); color: #ffcf73; }

button.amp-btn { min-height: 34px; padding: 0 16px; border-radius: 8px; border: 1px solid #3a372f;
                 background: #1e1d1b; color: #ece6da; font-family: Barlow; font-weight: 500; box-shadow: none; }
button.amp-btn:hover { background: #262421; }
button.amp-btn:checked { background: #2b2417; border-color: #e7a83e; }
button.amp-btn.primary { background: #e7a83e; border-color: #e7a83e; color: #1a1408; font-weight: 600; }
button.amp-btn.primary:hover { background: #f0b552; }

.drawer { background: #161615; border-left: 1px solid #2b2925; box-shadow: -20px 0 40px rgba(0,0,0,.5); }
.lib-row { padding: 12px; border-radius: 10px; background: #1e1d1b; border: 1px solid #2b2925; }
.lib-name { font-family: "Barlow Condensed"; font-weight: 600; font-size: 15px; letter-spacing: 1.5px; }
"""


def load_fonts():
    """Make the bundled Barlow fonts available to this process only."""
    if not os.path.isdir(FONTS):
        return
    try:
        fc = ctypes.CDLL('libfontconfig.so.1')
        fc.FcConfigAppFontAddDir.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddDir(None, FONTS.encode())
    except OSError:
        pass


def label(text, *classes, **kw):
    lab = Gtk.Label(label=text, **kw)
    for c in classes:
        lab.add_css_class(c)
    return lab


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Blackstar Amp')
        self.add_css_class('amp')
        self.set_default_size(1240, 820)
        self.set_size_request(380, 520)
        self.amp = None
        self.watch_id = 0
        self.updating = False
        self._last_hist = 0.0
        self.pending = {}
        self.flush_id = 0
        self.names = [''] * A.SLOTS
        self.voices = [0] * A.SLOTS
        self.active = None
        self.edited = False
        self.previewing = None
        self.focus = 'delay'
        self.knobs = {}
        self.base = None          # the stored patch the edits are compared to
        self.history = []         # (control, previous value) for Ctrl+Z
        self.undoing = False

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        tv = Adw.ToolbarView()
        tv.add_top_bar(self.build_header())
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self.build_offline(), 'offline')
        self.stack.add_named(self.build_main(), 'main')
        tv.set_content(self.stack)
        self.toasts.set_child(tv)
        self.install_actions()
        sc = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
        sc.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string('<Control>z'),
                                         Gtk.CallbackAction.new(lambda *_: self.undo() or True)))
        sc.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string('<Control><Shift>z'),
                                         Gtk.CallbackAction.new(lambda *_: self.revert_all() or True)))
        sc.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string('<Control>s'),
                                         Gtk.CallbackAction.new(lambda *_: self.guard(self.save_current) or True)))
        self.add_controller(sc)
        self.set_focus_fx(self.focus)

        self.connect('close-request', lambda *_: self.disconnect_amp() or False)
        self.try_connect()
        GLib.timeout_add_seconds(2, self.reconnect_tick)

    # ------------------------------------------------------------------
    # Construction
    def build_header(self):
        hb = Adw.HeaderBar()
        left = Gtk.Box(spacing=10, margin_start=6)
        self.conn_led = led()
        self.conn_led.add_css_class('green')
        left.append(self.conn_led)
        self.conn_label = label('Not connected', 'conn')
        left.append(self.conn_label)
        hb.pack_start(left)

        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.title_main = label('ID:CORE', 'title-main')
        self.title_sub = label('', 'title-sub')
        title.append(self.title_main)
        title.append(self.title_sub)
        hb.set_title_widget(title)

        hb.pack_end(self.menu_button())
        self.save_btn = Gtk.Button(label='Save')
        self.save_btn.add_css_class('amp-btn')
        self.save_btn.add_css_class('primary')
        self.save_btn.set_tooltip_text('Store the current sound in the selected slot')
        self.save_btn.connect('clicked', lambda *_: self.guard(self.save_current))
        hb.pack_end(self.save_btn)
        self.lib_btn = Gtk.ToggleButton(label='Library')
        self.lib_btn.add_css_class('amp-btn')
        self.lib_btn.connect('toggled', lambda b: self.drawer.set_reveal_child(b.get_active()))
        hb.pack_end(self.lib_btn)
        self.revert_all_btn = Gtk.Button(label='Revert all', visible=False)
        self.revert_all_btn.add_css_class('amp-btn')
        self.revert_all_btn.set_tooltip_text('Undo every change since the patch was loaded (Ctrl+Shift+Z)')
        self.revert_all_btn.connect('clicked', lambda *_: self.revert_all())
        hb.pack_end(self.revert_all_btn)
        return hb

    def build_offline(self):
        sp = Adw.StatusPage(icon_name='audio-speakers-symbolic', title='Amp not connected',
                            description='Connect the ID:Core over USB and switch it on.\n'
                                        'If it was already on, power-cycle it with the cable plugged in.')
        sp.add_css_class('amp-bg')
        btn = Gtk.Button(label='Try again', halign=Gtk.Align.CENTER)
        btn.add_css_class('amp-btn')
        btn.add_css_class('primary')
        btn.connect('clicked', lambda *_: self.try_connect(verbose=True))
        sp.set_child(btn)
        return sp

    def build_main(self):
        overlay = Gtk.Overlay()
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sw.add_css_class('amp-bg')
        clamp = Adw.Clamp(maximum_size=1360, tightening_threshold=1200)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                       margin_top=26, margin_bottom=30, margin_start=28, margin_end=28)
        body.append(self.build_plate())

        bottom = Gtk.Box(spacing=22)
        bottom.append(self.build_patches())
        bottom.append(self.build_fx_card())
        body.append(bottom)
        clamp.set_child(body)
        sw.set_child(clamp)
        overlay.set_child(sw)

        self.drawer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
                                   halign=Gtk.Align.END, valign=Gtk.Align.FILL)
        self.drawer.set_child(self.build_library())
        overlay.add_overlay(self.drawer)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 1000sp'))
        bp.add_setter(bottom, 'orientation', Gtk.Orientation.VERTICAL)
        self.add_breakpoint(bp)
        return overlay

    def section(self, title, child, last=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class('plate-section')
        if last:
            box.add_css_class('last')
        box.append(label(title.upper(), 'section-title', xalign=0))
        box.append(child)
        return box

    def knob(self, ctl, title, kind, size=96, ends=('0', '10')):
        _cid, lo, hi = A.CONTROLS[ctl]
        k = KnobControl(title, lo, hi, kind, size, ends)
        if size < 96:
            k.add_css_class('small')
        k.connect_changed(lambda v, ctl=ctl: self.queue(ctl, v))
        k.on_revert = lambda ctl=ctl: self.revert(ctl)
        self.knobs[ctl] = k
        return k

    def build_plate(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.voice = VoiceSelector(VOICE_SHORT)
        self.voice.connect('changed', lambda _w, v: self.queue('voice', v))
        vbox.append(self.voice)
        vrow = Gtk.Box(halign=Gtk.Align.CENTER)
        vrow.append(Gtk.Box(width_request=22))
        self.voice_name = label('', 'knob-value', 'voice-name')
        vrow.append(self.voice_name)
        self.voice_revert = revert_button(lambda: self.revert('voice'))
        vrow.append(self.voice_revert)
        vbox.append(vrow)

        pre = Gtk.Box(spacing=6)
        pre.append(self.knob('gain', 'Gain', 'knob'))
        pre.append(self.knob('volume', 'Volume', 'knob'))

        tone = Gtk.Box(spacing=6)
        for ctl, title in (('bass', 'Bass'), ('middle', 'Middle'), ('treble', 'Treble')):
            tone.append(self.knob(ctl, title, 'knob'))
        tone.append(self.knob('isf', 'ISF', 'knob', ends=('USA', 'UK')))

        fx = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.fx_buttons = {}
        for key, short, _long, _t, _types in FX:
            b = Gtk.Button()
            b.add_css_class('fx')
            row = Gtk.Box(spacing=10)
            b.led = led()
            row.append(b.led)
            row.append(Gtk.Label(label=short.upper(), xalign=0))
            b.set_child(row)
            b.connect('clicked', self.on_fx_button, key)
            line = Gtk.Box(spacing=4)
            line.append(b)
            b.revert = revert_button(lambda key=key: self.revert(key))
            line.append(b.revert)
            fx.append(line)
            self.fx_buttons[key] = b

        # The sections wrap onto a second row when the window is narrow.
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                           min_children_per_line=1, max_children_per_line=4,
                           row_spacing=18, valign=Gtk.Align.START, hexpand=True,
                           margin_top=22, margin_bottom=18, margin_start=8, margin_end=8)
        sections = (('Voice', vbox), ('Preamp', pre), ('Tone', tone), ('Effects', fx))
        for i, (title, child) in enumerate(sections):
            flow.append(self.section(title, child, last=i == len(sections) - 1))
        plate = Gtk.Box()
        plate.add_css_class('plate')
        plate.append(flow)
        return plate

    def build_patches(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True)
        head = Gtk.Box()
        head.append(label('PATCHES ON THE AMP', 'section-title', xalign=0, hexpand=True))
        head.append(label('Knobs: drag, scroll, or click the value to type it', 'hint'))
        box.append(head)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        self.tiles = []
        for i in range(A.SLOTS):
            b = Gtk.Button(hexpand=True)
            b.add_css_class('tile')
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            top = Gtk.Box()
            top.append(label(str(i + 1), 'tile-num', xalign=0, hexpand=True))
            b.led = led()
            top.append(b.led)
            v.append(top)
            b.name = label('', 'tile-name', xalign=0, ellipsize=3)
            b.voice = label('', 'tile-voice', xalign=0)
            v.append(b.name)
            v.append(b.voice)
            b.set_child(v)
            b.connect('clicked', self.on_tile, i + 1)
            grid.attach(b, i % 3, i // 3, 1, 1)
            self.tiles.append(b)
        box.append(grid)
        return box

    def build_fx_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, width_request=400)
        card.add_css_class('plate')
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                        margin_top=18, margin_bottom=18, margin_start=20, margin_end=20)
        head = Gtk.Box()
        self.fx_title = label('DELAY', 'section-title', xalign=0, hexpand=True)
        head.append(self.fx_title)
        self.fx_led = led()
        head.append(self.fx_led)
        inner.append(head)

        tabs = Gtk.Box(homogeneous=True, overflow=Gtk.Overflow.HIDDEN)
        tabs.add_css_class('seg')
        self.fx_tabs = {}
        group = None
        for key, _s, long, _t, _types in FX:
            tb = Gtk.ToggleButton(label=long.upper())
            if group:
                tb.set_group(group)
            group = group or tb
            tb.connect('toggled', lambda b, key=key: b.get_active() and self.set_focus_fx(key))
            tabs.append(tb)
            self.fx_tabs[key] = tb
        inner.append(tabs)

        self.fx_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.type_buttons = {}
        for key, _s, _l, type_ctl, types in FX:
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            seg = Gtk.Box(homogeneous=True, overflow=Gtk.Overflow.HIDDEN)
            seg.add_css_class('seg')
            group, btns = None, []
            for i, t in enumerate(types):
                b = Gtk.ToggleButton(label=t.upper())
                if group:
                    b.set_group(group)
                group = group or b
                b.connect('toggled', self.on_type, type_ctl, i)
                seg.append(b)
                btns.append(b)
            self.type_buttons[type_ctl] = btns
            seg.set_hexpand(True)
            line = Gtk.Box(spacing=4)
            line.append(seg)
            btns[0].revert = revert_button(lambda c=type_ctl: self.revert(c))
            line.append(btns[0].revert)
            page.append(line)
            row = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER, homogeneous=True)
            for ctl, title, kind in FX_KNOBS[key]:
                row.append(self.knob(ctl, title, kind, size=72, ends=None))
            page.append(row)
            self.fx_stack.add_named(page, key)
        inner.append(self.fx_stack)
        card.append(inner)
        return card

    def build_library(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, width_request=340)
        box.add_css_class('drawer')
        head = Gtk.Box(margin_top=18, margin_start=18, margin_end=18)
        head.append(label('LIBRARY', 'section-title', xalign=0, hexpand=True))
        close = Gtk.Button(label='Close')
        close.add_css_class('amp-btn')
        close.connect('clicked', lambda *_: self.lib_btn.set_active(False))
        head.append(close)
        box.append(head)
        box.append(label('Try a patch live, then Save it, or write it straight to a slot.',
                         'hint', xalign=0, wrap=True, margin_start=18, margin_end=18))
        self.lib_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                margin_start=18, margin_end=18)
        sw = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sw.set_child(self.lib_list)
        box.append(sw)
        foot = Gtk.Box(spacing=8, margin_start=18, margin_end=18, margin_bottom=18, homogeneous=True)
        bank = Gtk.Button(label='Write whole bank')
        bank.add_css_class('amp-btn')
        bank.set_tooltip_text('Store every library patch that names a slot (a backup is taken first)')
        bank.connect('clicked', lambda *_: self.confirm(
            'Write the whole bank?',
            'Slots 1-6 are replaced by the library patches. A backup of the current slots is taken first.',
            'Write', self.write_bank))
        folder = Gtk.Button(label='Open folder')
        folder.add_css_class('amp-btn')
        folder.connect('clicked', lambda *_: self.open_library())
        foot.append(bank)
        foot.append(folder)
        box.append(foot)
        self.fill_library()
        return box

    def menu_button(self):
        menu = Gio.Menu()
        s1 = Gio.Menu()
        s1.append('Save to slot…', 'win.save-as')
        s1.append('Rename slot…', 'win.rename')
        s1.append('Save to library…', 'win.to-library')
        menu.append_section(None, s1)
        s2 = Gio.Menu()
        s2.append('Back up all slots', 'win.backup')
        s2.append('Restore last backup…', 'win.restore')
        menu.append_section(None, s2)
        s3 = Gio.Menu()
        s3.append('Reload from amp', 'win.refresh')
        menu.append_section(None, s3)
        return Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu)

    def install_actions(self):
        for name, cb in (('save-as', lambda: self.save_dialog()),
                         ('rename', lambda: self.save_dialog(rename=True)),
                         ('to-library', lambda: self.library_dialog()),
                         ('backup', self.do_backup),
                         ('restore', lambda: self.confirm(
                             'Restore the last backup?',
                             (P.backups() or ['no backups yet'])[0],
                             'Restore', self.do_restore)),
                         ('refresh', self.refresh_all)):
            act = Gio.SimpleAction.new(name, None)
            act.connect('activate', lambda _a, _p, cb=cb: self.guard(cb))
            self.add_action(act)

    # ------------------------------------------------------------------
    # Connection
    def try_connect(self, verbose=False):
        if self.amp:
            return True
        try:
            if os.environ.get('BSAMP_FAKE'):
                from .fake import FakeTransport
                self.amp = A.Amp(FakeTransport())
            else:
                self.amp = A.Amp()
        except A.AmpError as e:
            if verbose:
                self.toast(str(e))
            self.show_offline()
            return False
        self.amp.listeners.append(self.on_event)
        self.watch_id = GLib.io_add_watch(
            self.amp.fileno(), GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR, self.on_io)
        try:
            self.refresh_all()
        except (A.AmpError, OSError) as e:
            self.toast(str(e))
            self.disconnect_amp()
            return False
        self.active = self.active or self.amp.slot
        self.stack.set_visible_child_name('main')
        set_led(self.conn_led, True)
        self.conn_label.set_label(f'{self.amp.model} · USB')
        self.update_title()
        return True

    def show_offline(self):
        self.stack.set_visible_child_name('offline')
        set_led(self.conn_led, False)
        self.conn_label.set_label('Not connected')
        self.title_main.set_label('ID:CORE')
        self.title_sub.set_label('')

    def disconnect_amp(self):
        if self.watch_id:
            GLib.source_remove(self.watch_id)
            self.watch_id = 0
        if self.amp:
            try:
                self.amp.close()
            except OSError:
                pass
        self.amp = None
        self.show_offline()

    def reconnect_tick(self):
        if not self.amp:
            self.try_connect()
        return True

    def on_io(self, fd, cond):
        if cond & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            self.disconnect_amp()
            return False
        try:
            self.amp.pump(0)
        except OSError:
            self.disconnect_amp()
            return False
        return True

    def guard(self, fn, *args):
        """Run an amp operation and turn errors into toasts."""
        if not self.amp:
            self.toast('Amp not connected')
            return None
        try:
            return fn(*args)
        except A.AmpError as e:
            self.toast(str(e))
        except OSError as e:
            self.toast(str(e))
            self.disconnect_amp()
        return None

    # ------------------------------------------------------------------
    # Amp -> UI
    def on_event(self, ev):
        t = ev['type']
        if t == 'state':
            self.show_settings(ev['settings'])
        elif t == 'slot':
            self.set_active(ev['slot'])
        elif t == 'manual' and ev['manual']:
            self.mark_edited()

    def refresh_all(self):
        self.names = self.amp.names()
        self.voices = [A.decode(self.amp.preset_raw(i))['voice'] for i in range(1, A.SLOTS + 1)]
        for b, name, v in zip(self.tiles, self.names, self.voices):
            b.name.set_label(name or 'EMPTY')
            b.name.set_opacity(1 if name else .5)
            b.voice.set_label(A.VOICES[v] if v < len(A.VOICES) else '')
        cur = self.amp.refresh()
        slot = self.active or self.amp.slot
        self.rebase(A.decode(self.amp.preset_raw(slot)) if slot else cur)
        self.show_settings(cur)
        self.update_title()

    def rebase(self, s):
        """Remember ``s`` as the patch that edits are compared to."""
        self.base = dict(s)
        self.history.clear()
        self.update_dirty()

    def current(self):
        cur = dict(getattr(self, 'last', None) or {})
        cur.update(self.pending)
        return cur

    def base_text(self, ctl):
        v = self.base[ctl]
        if ctl in self.knobs:
            return self.knobs[ctl].text(v)
        if ctl == 'voice':
            return A.VOICES[v] if v < 6 else str(v)
        if ctl in self.type_buttons:
            return self.type_buttons[ctl][v].get_label().title() if v < 4 else str(v)
        return 'on' if v else 'off'

    def update_dirty(self):
        if not self.base or not getattr(self, 'last', None):
            return
        cur = self.current()
        diff = lambda c: cur.get(c) != self.base.get(c)  # noqa: E731
        any_dirty = False
        for ctl, k in self.knobs.items():
            d = diff(ctl)
            k.set_dirty(d, self.base_text(ctl))
            any_dirty |= d
        d = diff('voice')
        set_revert(self.voice_revert, d, self.base_text('voice'))
        (self.voice_name.add_css_class if d else self.voice_name.remove_css_class)('dirty')
        any_dirty |= d
        for key, b in self.fx_buttons.items():
            d = diff(key)
            set_revert(b.revert, d, self.base_text(key))
            (b.add_css_class if d else b.remove_css_class)('dirty')
            any_dirty |= d
        for ctl, btns in self.type_buttons.items():
            d = diff(ctl)
            set_revert(btns[0].revert, d, self.base_text(ctl))
            any_dirty |= d
        self.revert_all_btn.set_visible(any_dirty)

    def set_controls(self, values, record=True):
        """Change controls from code (revert/undo): update the UI and send."""
        merged = self.current()
        merged.update(values)
        self.undoing = not record
        for ctl, v in values.items():
            self.queue(ctl, v)
        self.undoing = False
        self.show_settings(merged, keep_pending=False)

    def revert(self, ctl):
        if self.base and ctl in self.base:
            self.set_controls({ctl: self.base[ctl]})

    def revert_all(self):
        if not self.base:
            return
        cur = self.current()
        changed = {c: v for c, v in self.base.items()
                   if c in A.CONTROLS and c not in A.READ_ONLY and cur.get(c) != v}
        if changed:
            self.set_controls(changed)
            self.toast(f'Reverted {len(changed)} change' + ('s' if len(changed) > 1 else ''))

    def undo(self):
        if not self.history:
            self.toast('Nothing to undo')
            return
        ctl, old = self.history.pop()
        self.set_controls({ctl: old}, record=False)

    def show_settings(self, s, keep_pending=True):
        self.updating = True
        try:
            skip = self.pending if keep_pending else {}
            for ctl, k in self.knobs.items():
                if ctl not in skip:
                    k.set_value(s[ctl])
            if 'voice' not in skip:
                self.voice.set_value(s['voice'])
            self.voice_name.set_label(A.VOICES[s['voice']] if s['voice'] < 6 else '')
            for key, b in self.fx_buttons.items():
                set_led(b.led, bool(s[key]))
            set_led(self.fx_led, bool(s[self.focus]))
            for ctl, btns in self.type_buttons.items():
                if s[ctl] < len(btns):
                    btns[s[ctl]].set_active(True)
            self.knobs['mod_manual'].set_sensitive(s['mod_type'] == 1)
            self.last = dict(s)
        finally:
            self.updating = False
        self.update_dirty()

    def set_active(self, slot):
        self.active = slot
        self.edited = False
        self.previewing = None
        self.update_title()

    def mark_edited(self):
        if not self.edited:
            self.edited = True
            self.update_title()

    def update_title(self):
        if self.previewing:
            title, sub = self.previewing, 'Library preview · not saved'
        elif self.active:
            title = self.names[self.active - 1] or f'SLOT {self.active}'
            sub = f'Slot {self.active}' + (' · edited' if self.edited else '')
        else:
            title, sub = 'MANUAL', 'Not stored in a slot'
        self.title_main.set_label(title.upper())
        self.title_sub.set_label(sub)
        for i, b in enumerate(self.tiles):
            on = self.active == i + 1 and not self.previewing
            (b.add_css_class if on else b.remove_css_class)('on')
            set_led(b.led, on)

    def set_focus_fx(self, key):
        self.focus = key
        self.fx_stack.set_visible_child_name(key)
        self.fx_title.set_label(dict((k, l) for k, _s, l, _t, _y in FX)[key].upper())
        if not self.fx_tabs[key].get_active():
            self.fx_tabs[key].set_active(True)
        for k, b in self.fx_buttons.items():
            (b.add_css_class if k == key else b.remove_css_class)('focus')
        if hasattr(self, 'last'):
            set_led(self.fx_led, bool(self.last[key]))

    # ------------------------------------------------------------------
    # UI -> amp
    def queue(self, ctl, value):
        if self.updating:
            return
        if not self.undoing and ctl != 'fx_focus':
            old = self.current().get(ctl)
            now = time.monotonic()
            # one undo step per gesture: merge quick successive changes
            if old is not None and old != int(value) and not (
                    self.history and self.history[-1][0] == ctl and now - self._last_hist < 1.0):
                self.history.append((ctl, old))
                del self.history[:-200]
            self._last_hist = now
        self.pending[ctl] = int(value)
        if ctl == 'voice':
            self.voice_name.set_label(A.VOICES[int(value)])
        if not self.flush_id:
            self.flush_id = GLib.timeout_add(35, self.flush)
        self.update_dirty()

    def flush(self):
        self.flush_id = 0
        pending, self.pending = self.pending, {}
        for ctl, v in pending.items():
            self.guard(self.amp.set, ctl, v)
        if self.amp and pending:
            self.last = dict(self.amp.settings())
        self.update_dirty()
        self.mark_edited()
        return False

    def on_fx_button(self, b, key):
        s = self.amp.settings() if self.amp else None
        if not s:
            return
        on = not s[key]
        set_led(b.led, on)
        self.queue(key, 1 if on else 0)
        if on:
            self.queue('fx_focus', [k for k, *_ in FX].index(key) + 1)
        self.set_focus_fx(key)
        set_led(self.fx_led, on)

    def on_type(self, b, ctl, i):
        if b.get_active():
            if ctl == 'mod_type':
                self.knobs['mod_manual'].set_sensitive(i == 1)
            self.queue(ctl, i)

    def on_tile(self, _b, slot):
        def go():
            self.amp.select(slot)
            self.set_active(slot)
            self.amp.pump(0.15)
            cur = self.amp.refresh()
            self.rebase(cur)
            self.show_settings(cur)
        self.guard(go)

    # ------------------------------------------------------------------
    # Library
    def fill_library(self):
        while (child := self.lib_list.get_first_child()):
            self.lib_list.remove(child)
        for doc, path, user in P.library():
            row = Gtk.Box(spacing=10)
            row.add_css_class('lib-row')
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, spacing=2)
            text.append(label(doc['name'].upper(), 'lib-name', xalign=0, ellipsize=3))
            sub = doc['voice'] + (f" · slot {doc['slot']}" if doc.get('slot') else '') + (' · yours' if user else '')
            text.append(label(sub, 'tile-voice', xalign=0))
            row.append(text)
            if doc.get('notes'):
                row.set_tooltip_text(doc['notes'])
            tryb = Gtk.Button(label='Try', valign=Gtk.Align.CENTER)
            tryb.add_css_class('amp-btn')
            tryb.connect('clicked', lambda _b, doc=doc: self.guard(self.preview, doc))
            row.append(tryb)
            row.append(self.write_menu(doc))
            self.lib_list.append(row)

    def write_menu(self, doc):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6,
                      margin_bottom=6, margin_start=6, margin_end=6)
        title = Gtk.Label(label=f"Write {doc['name']} to", xalign=0, margin_bottom=4)
        title.add_css_class('heading')
        box.append(title)
        btns = []
        for i in range(1, A.SLOTS + 1):
            b = Gtk.Button()
            b.add_css_class('flat')
            b.connect('clicked', lambda _b, i=i: (pop.popdown(),
                                                  self.guard(self.write_patch, i, doc)))
            box.append(b)
            btns.append(b)
        pop.set_child(box)

        def refresh(*_):
            for i, b in enumerate(btns):
                b.set_label(f'{i + 1}   {self.names[i] or "Empty"}')
        pop.connect('show', refresh)
        mb = Gtk.MenuButton(icon_name='document-save-symbolic', popover=pop,
                            valign=Gtk.Align.CENTER, tooltip_text='Write to a slot')
        mb.add_css_class('amp-btn')
        return mb

    def preview(self, doc):
        self.amp.apply(P.to_settings(doc))
        self.amp.pump(0.1)
        self.previewing = doc['name']
        self.edited = True
        self.rebase(self.amp.settings())
        self.show_settings(self.amp.settings())
        self.update_title()

    def write_patch(self, slot, doc):
        b = P.ensure_daily_backup(self.amp)
        self.amp.write_preset(slot, doc['name'], P.to_settings(doc))
        self.amp.select(slot)
        self.refresh_all()
        self.set_active(slot)
        self.toast(f"{A.clean_name(doc['name'])} → slot {slot}" + (' (backup taken)' if b else ''))

    def write_bank(self):
        P.ensure_daily_backup(self.amp)
        n = 0
        for doc in P.bank():
            self.amp.write_preset(doc['slot'], doc['name'], P.to_settings(doc))
            n += 1
        self.refresh_all()
        self.toast(f'{n} patches written (backup taken)')

    # ------------------------------------------------------------------
    # Saving
    def save_current(self, slot=None, name=None):
        slot = slot or self.active
        if not slot:
            return self.save_dialog()
        name = name or self.previewing or self.names[slot - 1] or f'PATCH {slot}'
        P.ensure_daily_backup(self.amp)
        self.amp.write_preset(slot, name, self.amp.refresh())
        self.amp.select(slot)
        self.refresh_all()
        self.set_active(slot)
        self.toast(f'Saved to slot {slot}')

    def save_dialog(self, rename=False):
        d = Adw.AlertDialog(heading='Rename slot' if rename else 'Save to slot')
        group = Adw.PreferencesGroup()
        slot_row = Adw.ComboRow(title='Slot', model=Gtk.StringList.new(
            [f'{i + 1}  {n or "Empty"}' for i, n in enumerate(self.names)]))
        slot_row.set_selected((self.active or 1) - 1)
        name_row = Adw.EntryRow(title='Name')
        name_row.set_text(self.previewing or (self.names[(self.active or 1) - 1]))
        slot_row.connect('notify::selected', lambda r, _p: rename and name_row.set_text(
            self.names[r.get_selected()]))
        group.add(slot_row)
        group.add(name_row)
        d.set_extra_child(group)
        d.add_response('cancel', 'Cancel')
        d.add_response('ok', 'Rename' if rename else 'Save')
        d.set_response_appearance('ok', Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response('ok')

        def done(_d, resp):
            if resp != 'ok':
                return
            slot = slot_row.get_selected() + 1
            name = name_row.get_text().strip() or f'PATCH {slot}'
            if rename:
                def go():
                    P.ensure_daily_backup(self.amp)
                    self.amp.write_preset(slot, name)
                    self.refresh_all()
                    self.toast(f'Slot {slot} renamed')
                self.guard(go)
            else:
                self.guard(self.save_current, slot, name)
        d.connect('response', done)
        d.present(self)

    def library_dialog(self):
        d = Adw.AlertDialog(heading='Save to library',
                            body='Keeps the current sound as a patch file you can write to any slot later.')
        group = Adw.PreferencesGroup()
        name_row = Adw.EntryRow(title='Name')
        name_row.set_text(self.previewing or (self.names[self.active - 1] if self.active else ''))
        group.add(name_row)
        d.set_extra_child(group)
        d.add_response('cancel', 'Cancel')
        d.add_response('ok', 'Save')
        d.set_response_appearance('ok', Adw.ResponseAppearance.SUGGESTED)

        def done(_d, resp):
            if resp != 'ok':
                return
            name = A.clean_name(name_row.get_text()) or 'MY PATCH'

            def go():
                doc = P.from_settings(self.amp.refresh(), name)
                P.save(doc, os.path.join(P.USER, P.slug(name) + '.json'))
                self.fill_library()
                self.toast(f'Saved {name} to the library')
            self.guard(go)
        d.connect('response', done)
        d.present(self)

    def do_backup(self):
        path = P.backup(self.amp)
        self.toast(f'Backup: {os.path.basename(path)}')

    def do_restore(self):
        b = P.backups()
        if not b:
            return self.toast('No backups yet')
        P.restore(self.amp, b[0])
        self.refresh_all()
        self.toast('Backup restored')

    def open_library(self):
        os.makedirs(P.USER, exist_ok=True)
        Gtk.FileLauncher.new(Gio.File.new_for_path(P.USER)).launch(self, None, None, None)

    # ------------------------------------------------------------------
    def confirm(self, heading, body, action, fn):
        d = Adw.AlertDialog(heading=heading, body=body)
        d.add_response('cancel', 'Cancel')
        d.add_response('ok', action)
        d.set_response_appearance('ok', Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect('response', lambda _d, r: r == 'ok' and self.guard(fn))
        d.present(self)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=3))


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.win = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        css = Gtk.CssProvider()
        css.load_from_string(CSS) if hasattr(css, 'load_from_string') else css.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        if not self.win:
            self.win = Window(self)
        self.win.present()


def main():
    load_fonts()
    return App().run(sys.argv[:1])
