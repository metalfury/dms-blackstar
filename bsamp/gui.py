"""Blackstar Amp - a GTK 4 / libadwaita app for the ID:Core."""

import os
import sys

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import amp as A  # noqa: E402
from . import presets as P  # noqa: E402

APP_ID = 'io.github.metalfury.bsamp'

CSS = b"""
.slot-badge {
  min-width: 26px; min-height: 26px; border-radius: 99px;
  font-weight: bold; font-feature-settings: "tnum";
  background: alpha(currentColor, .08);
}
.slot-row.active { background: alpha(@accent_bg_color, .16); }
.slot-row.active .slot-badge { background: @accent_bg_color; color: @accent_fg_color; }
.voice-switch button { padding: 6px 10px; }
.knob-value { font-feature-settings: "tnum"; min-width: 40px; }
.fx-off row { opacity: .55; }
"""

# (control, label, kind) - kind: knob (0..127 shown 0..10), seg (0..31), ms
AMP_ROWS = [('gain', 'Gain', 'knob'), ('volume', 'Volume', 'knob'),
            ('bass', 'Bass', 'knob'), ('middle', 'Middle', 'knob'),
            ('treble', 'Treble', 'knob'), ('isf', 'ISF', 'knob')]
FX_ROWS = {
    'mod': ('Modulation', 'mod_type', A.MOD_TYPES,
            [('mod_level', 'Level', 'knob'), ('mod_speed', 'Speed', 'knob'),
             ('mod_segval', 'Amount', 'seg'), ('mod_manual', 'Manual (flanger)', 'knob')]),
    'delay': ('Delay', 'delay_type', A.DELAY_TYPES,
              [('delay_time', 'Time', 'ms'), ('delay_feedback', 'Feedback', 'seg'),
               ('delay_level', 'Level', 'knob')]),
    'reverb': ('Reverb', 'reverb_type', A.REVERB_TYPES,
               [('reverb_size', 'Size', 'seg'), ('reverb_level', 'Level', 'knob')]),
}
SUBTITLES = {'isf': 'USA  ←→  UK'}


def fmt(kind, v):
    if kind == 'knob':
        return f'{v / 12.7:.1f}'
    if kind == 'ms':
        return f'{int(v)} ms'
    return str(int(v))


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Blackstar Amp')
        self.set_default_size(1000, 760)
        self.set_size_request(360, 480)
        self.amp = None
        self.watch_id = 0
        self.updating = False
        self.pending = {}
        self.flush_id = 0
        self.names = [''] * A.SLOTS
        self.active = None        # last selected slot
        self.edited = False
        self.previewing = None    # library patch shown live but not saved
        self.scales = {}
        self.fx = {}
        self.combos = {}

        self.toasts = Adw.ToastOverlay()
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.toasts.set_child(self.stack)
        self.set_content(self.toasts)

        self.stack.add_named(self.build_offline(), 'offline')
        self.stack.add_named(self.build_main(), 'main')
        self.install_actions()

        self.connect('close-request', lambda *_: self.disconnect_amp() or False)
        self.try_connect()
        GLib.timeout_add_seconds(2, self.reconnect_tick)

    # ------------------------------------------------------------------
    # UI construction
    def build_offline(self):
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        sp = Adw.StatusPage(icon_name='audio-input-microphone-symbolic',
                            title='Amp not connected',
                            description='Connect the ID:Core over USB and switch it on.\n'
                                        'If it was already on, power-cycle it with the cable plugged in.')
        btn = Gtk.Button(label='Try again', halign=Gtk.Align.CENTER)
        btn.add_css_class('pill')
        btn.add_css_class('suggested-action')
        btn.connect('clicked', lambda *_: self.try_connect(verbose=True))
        sp.set_child(btn)
        tv.set_content(sp)
        return tv

    def build_main(self):
        split = Adw.NavigationSplitView(min_sidebar_width=260, max_sidebar_width=320)
        split.set_sidebar(self.build_sidebar())
        split.set_content(self.build_content())
        self.split = split
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 720sp'))
        bp.add_setter(split, 'collapsed', True)
        self.add_breakpoint(bp)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 560sp'))
        narrow.add_setter(split, 'collapsed', True)
        narrow.add_setter(self.voice_row, 'visible', False)
        narrow.add_setter(self.voice_combo, 'visible', True)
        for sc, _v, _k in self.scales.values():
            narrow.add_setter(sc, 'width-request', 150)
        self.add_breakpoint(narrow)
        return split

    def build_sidebar(self):
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title='Patches'))
        tv.add_top_bar(hb)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=6, margin_bottom=12, margin_start=6, margin_end=6)

        box.append(self.section_label('On the amp'))
        self.slot_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.slot_list.add_css_class('navigation-sidebar')
        self.slot_rows = []
        for i in range(1, A.SLOTS + 1):
            row = Gtk.ListBoxRow()
            row.add_css_class('slot-row')
            h = Gtk.Box(spacing=10, margin_top=4, margin_bottom=4)
            badge = Gtk.Label(label=str(i), valign=Gtk.Align.CENTER)
            badge.add_css_class('slot-badge')
            name = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
            voice = Gtk.Label(xalign=1)
            voice.add_css_class('dim-label')
            voice.add_css_class('caption')
            h.append(badge)
            h.append(name)
            h.append(voice)
            row.set_child(h)
            row.slot = i
            row.name_label = name
            row.voice_label = voice
            self.slot_list.append(row)
            self.slot_rows.append(row)
        self.slot_list.connect('row-activated', self.on_slot_activated)
        box.append(self.slot_list)

        box.append(self.section_label('Library'))
        self.lib_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lib_list.add_css_class('navigation-sidebar')
        self.lib_list.connect('row-activated', self.on_library_activated)
        box.append(self.lib_list)

        bank = Gtk.Button(label='Write whole bank to amp', margin_top=6)
        bank.set_tooltip_text('Store every library patch that names a slot (a backup is taken first)')
        bank.connect('clicked', lambda *_: self.confirm(
            'Write the whole bank?',
            'Slots 1-6 are replaced by the library patches. A backup of the current slots is taken first.',
            'Write', self.write_bank))
        box.append(bank)

        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sw.set_child(box)
        tv.set_content(sw)
        self.fill_library()
        return Adw.NavigationPage(child=tv, title='Patches')

    def section_label(self, text):
        lbl = Gtk.Label(label=text, xalign=0, margin_start=12, margin_top=12, margin_bottom=2)
        lbl.add_css_class('heading')
        lbl.add_css_class('dim-label')
        return lbl

    def build_content(self):
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        self.title = Adw.WindowTitle(title='ID:Core')
        hb.set_title_widget(self.title)

        self.save_btn = Gtk.Button(label='Save')
        self.save_btn.add_css_class('suggested-action')
        self.save_btn.set_tooltip_text('Store the current sound in the selected slot')
        self.save_btn.connect('clicked', lambda *_: self.save_current())
        hb.pack_end(self.menu_button())
        hb.pack_end(self.save_btn)
        tv.add_top_bar(hb)

        page = Adw.PreferencesPage()

        amp = Adw.PreferencesGroup(title='Amp')
        vrow = Adw.ActionRow(title='Voice')
        vbox = Gtk.Box(valign=Gtk.Align.CENTER)
        vbox.add_css_class('linked')
        vbox.add_css_class('voice-switch')
        self.voice_buttons = []
        group = None
        for i, v in enumerate(A.VOICES):
            b = Gtk.ToggleButton(label=v)
            if group:
                b.set_group(group)
            group = group or b
            b.connect('toggled', self.on_voice_toggled, i)
            vbox.append(b)
            self.voice_buttons.append(b)
        vrow.add_suffix(vbox)
        amp.add(vrow)
        self.voice_row = vrow
        self.voice_combo = Adw.ComboRow(title='Voice', model=Gtk.StringList.new(A.VOICES),
                                        visible=False)
        self.voice_combo.connect('notify::selected', self.on_combo, 'voice')
        amp.add(self.voice_combo)
        for ctl, label, kind in AMP_ROWS:
            amp.add(self.scale_row(ctl, label, kind))
        page.add(amp)

        for fx, (title, type_ctl, types, rows) in FX_ROWS.items():
            g = Adw.PreferencesGroup(title=title)
            g.add_css_class('fx-off')
            sw = Gtk.Switch(valign=Gtk.Align.CENTER)
            sw.connect('notify::active', self.on_fx_switch, fx, g)
            g.set_header_suffix(sw)
            self.fx[fx] = sw
            combo = Adw.ComboRow(title='Type', model=Gtk.StringList.new(types))
            combo.connect('notify::selected', self.on_combo, type_ctl)
            self.combos[type_ctl] = combo
            g.add(combo)
            for ctl, label, kind in rows:
                g.add(self.scale_row(ctl, label, kind))
            page.add(g)

        tv.set_content(page)
        return Adw.NavigationPage(child=tv, title='Sound')

    def scale_row(self, ctl, label, kind):
        _, lo, hi = A.CONTROLS[ctl]
        row = Adw.ActionRow(title=label)
        if ctl in SUBTITLES:
            row.set_subtitle(SUBTITLES[ctl])
        step = 10 if kind == 'ms' else 1
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        sc.set_size_request(380, -1)
        sc.set_valign(Gtk.Align.CENTER)
        sc.set_draw_value(False)
        val = Gtk.Label(xalign=1)
        val.add_css_class('knob-value')
        val.add_css_class('numeric')
        sc.connect('value-changed', self.on_scale, ctl, kind, val)
        row.add_suffix(sc)
        row.add_suffix(val)
        self.scales[ctl] = (sc, val, kind)
        return row

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
        s2.append('Open library folder', 'win.open-library')
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
                         ('open-library', self.open_library),
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
            self.stack.set_visible_child_name('offline')
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
        self.stack.set_visible_child_name('main')
        return True

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
        self.stack.set_visible_child_name('offline')

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
        voices = []
        for i in range(1, A.SLOTS + 1):
            voices.append(A.decode(self.amp.preset_raw(i))['voice'])
        for row, name, v in zip(self.slot_rows, self.names, voices):
            row.name_label.set_label(name or 'Empty')
            row.name_label.set_opacity(1 if name else .5)
            row.voice_label.set_label(A.VOICES[v] if v < len(A.VOICES) else '')
        self.show_settings(self.amp.refresh())
        self.update_title()

    def show_settings(self, s):
        self.updating = True
        try:
            for ctl, (sc, val, kind) in self.scales.items():
                if ctl in self.pending:
                    continue
                sc.set_value(s[ctl])
                val.set_label(fmt(kind, s[ctl]))
            if s['voice'] < len(self.voice_buttons):
                self.voice_buttons[s['voice']].set_active(True)
                self.voice_combo.set_selected(s['voice'])
            for fx, sw in self.fx.items():
                sw.set_active(bool(s[fx]))
            for ctl, combo in self.combos.items():
                combo.set_selected(s[ctl])
            self.scales['mod_manual'][0].set_sensitive(s['mod_type'] == 1)
        finally:
            self.updating = False

    def set_active(self, slot):
        self.active = slot
        self.edited = False
        self.previewing = None
        for row in self.slot_rows:
            (row.add_css_class if row.slot == slot else row.remove_css_class)('active')
        self.update_title()

    def mark_edited(self):
        if not self.edited:
            self.edited = True
            self.update_title()

    def update_title(self):
        if self.previewing:
            title, sub = self.previewing, 'Library preview · not saved'
        elif self.active:
            title = self.names[self.active - 1] or f'Slot {self.active}'
            sub = f'Slot {self.active}' + (' · edited' if self.edited else '')
        else:
            title, sub = 'Manual', 'Not stored in a slot'
        model = self.amp.model if self.amp else ''
        self.title.set_title(title)
        self.title.set_subtitle(f'{model} · {sub}' if model else sub)

    # ------------------------------------------------------------------
    # UI -> amp
    def queue(self, ctl, value):
        self.pending[ctl] = int(value)
        if not self.flush_id:
            self.flush_id = GLib.timeout_add(35, self.flush)

    def flush(self):
        self.flush_id = 0
        pending, self.pending = self.pending, {}
        for ctl, v in pending.items():
            self.guard(self.amp.set, ctl, v)
        self.mark_edited()
        return False

    def on_scale(self, sc, ctl, kind, val):
        v = sc.get_value()
        val.set_label(fmt(kind, v))
        if not self.updating:
            self.queue(ctl, v)

    def on_voice_toggled(self, btn, idx):
        if btn.get_active() and not self.updating:
            self.queue('voice', idx)
            self.updating = True
            self.voice_combo.set_selected(idx)
            self.updating = False

    def on_fx_switch(self, sw, _p, fx, group):
        (group.remove_css_class if sw.get_active() else group.add_css_class)('fx-off')
        if not self.updating:
            self.queue(fx, 1 if sw.get_active() else 0)
            if sw.get_active():
                self.queue('fx_focus', ['mod', 'delay', 'reverb'].index(fx) + 1)

    def on_combo(self, combo, _p, ctl):
        if ctl == 'mod_type':
            self.scales['mod_manual'][0].set_sensitive(combo.get_selected() == 1)
        if ctl == 'voice' and not self.updating:
            self.updating = True
            self.voice_buttons[combo.get_selected()].set_active(True)
            self.updating = False
        if not self.updating:
            self.queue(ctl, combo.get_selected())

    def on_slot_activated(self, _lb, row):
        def go():
            self.amp.select(row.slot)
            self.set_active(row.slot)
            self.amp.pump(0.15)
            self.show_settings(self.amp.refresh())
        self.guard(go)
        if self.split.get_collapsed():
            self.split.set_show_content(True)

    # ------------------------------------------------------------------
    # Library
    def fill_library(self):
        while (child := self.lib_list.get_first_child()):
            self.lib_list.remove(child)
        for doc, path, user in P.library():
            row = Adw.ActionRow(title=doc['name'], activatable=True)
            row.set_subtitle(doc['voice'] + (f" · slot {doc['slot']}" if doc.get('slot') else '')
                             + (' · yours' if user else ''))
            if doc.get('notes'):
                row.set_tooltip_text(doc['notes'])
            row.doc = doc
            row.add_suffix(self.write_menu(doc))
            self.lib_list.append(row)

    def write_menu(self, doc):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6,
                      margin_bottom=6, margin_start=6, margin_end=6)
        title = Gtk.Label(label=f"Write “{doc['name']}” to", xalign=0, margin_bottom=4)
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
        mb.add_css_class('flat')
        return mb

    def on_library_activated(self, _lb, row):
        def go():
            self.amp.apply(P.to_settings(row.doc))
            self.amp.pump(0.1)
            self.previewing = row.doc['name']
            self.edited = True
            self.show_settings(self.amp.settings())
            self.update_title()
        self.guard(go)
        if self.split.get_collapsed():
            self.split.set_show_content(True)

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
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
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
        box.append(group)
        d.set_extra_child(box)
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
                path = os.path.join(P.USER, P.slug(name) + '.json')
                P.save(doc, path)
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
        css = Gtk.CssProvider()
        css.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        if not self.win:
            self.win = Window(self)
        self.win.present()


def main():
    return App().run(sys.argv[:1])
