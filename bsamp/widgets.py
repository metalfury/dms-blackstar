"""Hand-drawn amp controls for the app: knobs, the voice selector, LEDs."""

import math

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gdk, GObject, Gtk, Pango, PangoCairo  # noqa: E402

SWEEP = 270.0          # degrees of travel, centred on "up"


def rgb(h, a=1.0):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


def polar(cx, cy, r, deg):
    """Point at ``deg`` degrees clockwise from straight up."""
    a = math.radians(deg - 90)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def shadow(cr, cx, cy, r, dy, alpha, steps=6):
    for i in range(steps, 0, -1):
        cr.set_source_rgba(0, 0, 0, alpha / steps)
        cr.arc(cx, cy + dy, r + i * 1.4, 0, 2 * math.pi)
        cr.fill()


class Knob(Gtk.DrawingArea):
    """A silver-cap amp knob. Drag up/down, scroll or use the arrow keys."""

    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self, lo, hi, size=96, ticks=True, label=''):
        super().__init__(accessible_role=Gtk.AccessibleRole.SLIDER)
        self.lo, self.hi, self.value = lo, hi, lo
        self.ticks = ticks
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_focusable(True)
        self.set_cursor(Gdk.Cursor.new_from_name('ns-resize'))
        self.set_draw_func(self.draw)
        self.update_property([Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.VALUE_MIN,
                              Gtk.AccessibleProperty.VALUE_MAX], [label, float(lo), float(hi)])

        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self.on_drag_begin)
        drag.connect('drag-update', self.on_drag_update)
        self.add_controller(drag)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self.on_scroll)
        self.add_controller(scroll)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.on_key)
        self.add_controller(keys)
        self.connect('notify::has-focus', lambda *_: self.queue_draw())
        self._v0 = lo

    # -- value ----------------------------------------------------------
    def set_value(self, v):
        """Set without emitting ``changed`` (used for updates from the amp)."""
        v = max(self.lo, min(self.hi, int(v)))
        if v != self.value:
            self.value = v
            self.update_property([Gtk.AccessibleProperty.VALUE_NOW], [float(v)])
            self.queue_draw()

    def user_set(self, v):
        v = max(self.lo, min(self.hi, int(round(v))))
        if v != self.value:
            self.set_value(v)
            self.emit('changed', v)

    @property
    def step(self):
        return 10 if self.hi - self.lo > 200 else 1

    def on_drag_begin(self, g, x, y):
        self._v0 = self.value
        self.grab_focus()

    def on_drag_update(self, g, dx, dy):
        # Up or right turns it up; a full turn takes ~250 px (Shift: 4x finer)
        fine = g.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK
        span = (self.hi - self.lo) / (1000 if fine else 250)
        self.user_set(self._v0 + (dx - dy) * span)

    def on_scroll(self, c, dx, dy):
        # One wheel notch = 0.2 on the 0-10 scale (Shift: the smallest step)
        fine = c.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK
        step = self.step if fine else max(self.step, round((self.hi - self.lo) / 50))
        self.user_set(self.value - (1 if dy > 0 else -1) * step)
        return True

    def on_key(self, c, keyval, code, state):
        k = Gdk
        if keyval in (k.KEY_Up, k.KEY_Right, k.KEY_plus, k.KEY_KP_Add):
            self.user_set(self.value + self.step)
        elif keyval in (k.KEY_Down, k.KEY_Left, k.KEY_minus, k.KEY_KP_Subtract):
            self.user_set(self.value - self.step)
        elif keyval == k.KEY_Page_Up:
            self.user_set(self.value + (self.hi - self.lo) / 10)
        elif keyval == k.KEY_Page_Down:
            self.user_set(self.value - (self.hi - self.lo) / 10)
        elif keyval == k.KEY_Home:
            self.user_set(self.lo)
        elif keyval == k.KEY_End:
            self.user_set(self.hi)
        else:
            return False
        return True

    # -- drawing --------------------------------------------------------
    def draw(self, area, cr, w, h):
        s = min(w, h)
        cx, cy, R = w / 2, h / 2, s / 2
        frac = (self.value - self.lo) / (self.hi - self.lo)
        ang = -SWEEP / 2 + SWEEP * frac

        if self.ticks:
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for i in range(11):
                t = -SWEEP / 2 + SWEEP * i / 10
                x1, y1 = polar(cx, cy, R * (0.80 if i % 5 else 0.78), t)
                x2, y2 = polar(cx, cy, R * 0.95, t)
                cr.set_source_rgba(*rgb('#cfc7b6', 0.95 if i % 5 == 0 else 0.6))
                cr.set_line_width(1.8 if i % 5 == 0 else 1.3)
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()
            skirt = R * 0.68
        else:
            skirt = R * 0.86
        cap = skirt * 0.76

        # drop shadow and knurled skirt
        shadow(cr, cx, cy, skirt, R * 0.08, 0.55)
        cr.set_source_rgba(*rgb('#0b0b0b'))
        cr.arc(cx, cy, skirt, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(max(1.0, skirt * 0.06))
        for i in range(48):
            x1, y1 = polar(cx, cy, cap + (skirt - cap) * 0.15, i * 7.5)
            x2, y2 = polar(cx, cy, skirt * 0.97, i * 7.5)
            cr.set_source_rgba(1, 1, 1, 0.07 if i % 2 else 0.02)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
        g = cairo.LinearGradient(cx, cy - skirt, cx, cy + skirt)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.10)
        g.add_color_stop_rgba(0.5, 1, 1, 1, 0.0)
        cr.set_source(g)
        cr.arc(cx, cy, skirt, 0, 2 * math.pi)
        cr.fill()

        # brushed silver cap
        g = cairo.RadialGradient(cx - cap * 0.3, cy - cap * 0.4, cap * 0.05, cx, cy, cap * 1.05)
        for off, col in ((0, '#fbfbfb'), (0.25, '#d0d0d0'), (0.62, '#7e7e7e'), (1, '#3a3a3a')):
            g.add_color_stop_rgba(off, *rgb(col))
        cr.set_source(g)
        cr.arc(cx, cy, cap, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.85)
        cr.set_line_width(1)
        cr.stroke()

        # pointer
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(max(2.0, cap * 0.1))
        cr.set_source_rgba(*rgb('#151515'))
        x1, y1 = polar(cx, cy, cap * 0.38, ang)
        x2, y2 = polar(cx, cy, cap * 0.88, ang)
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()

        if self.has_focus():
            cr.set_source_rgba(*rgb('#e7a83e', 0.9))
            cr.set_line_width(2)
            cr.arc(cx, cy, R - 1.5, 0, 2 * math.pi)
            cr.stroke()


# How a raw control value is shown and typed: (to display, from display,
# display min, display max, step, digits, unit)
UNITS = {
    'knob': (lambda v: v / 12.7, lambda d: round(d * 12.7), 0, 10, 0.1, 1, ''),
    'seg': (float, round, 0, 31, 1, 0, ''),
    'ms': (float, lambda d: int(round(d / 10) * 10), 100, 2000, 10, 0, ' ms'),
}


class KnobControl(Gtk.Box):
    """Knob with its engraved name and a value readout.

    Besides dragging and scrolling, clicking the readout (or double-clicking
    the knob) opens a popover with a wide slider and a number field."""

    def __init__(self, label, lo, hi, kind, size=96, ends=('0', '10')):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                         halign=Gtk.Align.CENTER)
        self.kind = kind
        self.to_disp, self.from_disp, dlo, dhi, step, digits, self.unit = UNITS[kind]
        self.digits = digits
        self.add_css_class('knob-control')
        over = Gtk.Overlay()
        self.knob = Knob(lo, hi, size, label=label)
        over.set_child(self.knob)
        if ends:
            for text, align in zip(ends, (Gtk.Align.START, Gtk.Align.END)):
                lab = Gtk.Label(label=text, halign=align, valign=Gtk.Align.END)
                lab.add_css_class('knob-end')
                lab.set_can_target(False)
                over.add_overlay(lab)
        self.append(over)
        name = Gtk.Label(label=label.upper())
        name.add_css_class('knob-name')
        self.append(name)

        # readout = button that opens the fine-edit popover
        self.readout = Gtk.Button(halign=Gtk.Align.CENTER, tooltip_text='Set exact value')
        self.readout.add_css_class('knob-value-btn')
        pop = self.popover = Gtk.Popover()
        box = Gtk.Box(spacing=10, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        self.adj = Gtk.Adjustment(lower=dlo, upper=dhi, step_increment=step,
                                  page_increment=step * 10)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adj,
                          draw_value=False, width_request=260)
        spin = Gtk.SpinButton(adjustment=self.adj, digits=digits, numeric=True, width_chars=5)
        spin.connect('activate', lambda *_: pop.popdown())
        box.append(Gtk.Label(label=label))
        box.append(scale)
        box.append(spin)
        pop.set_child(box)
        pop.connect('show', lambda *_: spin.grab_focus())
        pop.set_parent(self.readout)
        self.readout.connect('clicked', lambda *_: pop.popup())
        self.append(self.readout)
        self._syncing = False
        self.adj.connect('value-changed', self.on_adj)

        dbl = Gtk.GestureClick()
        dbl.connect('pressed', lambda g, n, x, y: n == 2 and pop.popup())
        self.knob.add_controller(dbl)
        self.knob.connect('changed', lambda _k, v: self.sync(v))
        self.sync(lo)

    def text(self, v):
        d = self.to_disp(v)
        return (f'{d:.{self.digits}f}' if self.digits else str(int(d))) + self.unit

    def sync(self, v):
        self.readout.set_label(self.text(v))
        self._syncing = True
        self.adj.set_value(self.to_disp(v))
        self._syncing = False

    def on_adj(self, adj):
        if not self._syncing:
            self.knob.user_set(self.from_disp(adj.get_value()))

    def set_value(self, v):
        self.knob.set_value(v)
        self.sync(self.knob.value)

    def connect_changed(self, cb):
        self.knob.connect('changed', lambda _k, v: cb(v))


class VoiceSelector(Gtk.DrawingArea):
    """Six-position rotary switch with a chicken-head knob."""

    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, (int,))}
    W, H = 236, 158

    def __init__(self, labels):
        super().__init__(accessible_role=Gtk.AccessibleRole.SLIDER)
        self.labels = labels
        self.value = 0
        self.set_content_width(self.W)
        self.set_content_height(self.H)
        self.set_focusable(True)
        self.set_draw_func(self.draw)
        self.update_property([Gtk.AccessibleProperty.LABEL], ['Voice'])
        click = Gtk.GestureClick()
        click.connect('pressed', self.on_click)
        self.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', lambda *_: setattr(self, '_v0', self.value))
        drag.connect('drag-update', lambda g, dx, dy: self.user_set(self._v0 - round(dy / 28)))
        self.add_controller(drag)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', lambda c, dx, dy: self.user_set(self.value + (-1 if dy > 0 else 1)) or True)
        self.add_controller(scroll)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.on_key)
        self.add_controller(keys)
        self.connect('notify::has-focus', lambda *_: self.queue_draw())
        self._v0 = 0

    def angle(self, i):
        return -135 + 270 * i / (len(self.labels) - 1)

    def geometry(self, w, h):
        return w / 2, h / 2 + 10, 80

    def set_value(self, v):
        if v != self.value and 0 <= v < len(self.labels):
            self.value = v
            self.update_property([Gtk.AccessibleProperty.VALUE_TEXT], [self.labels[v]])
            self.queue_draw()

    def user_set(self, v):
        v = max(0, min(len(self.labels) - 1, int(v)))
        if v != self.value:
            self.set_value(v)
            self.emit('changed', v)

    def on_click(self, g, n, x, y):
        self.grab_focus()
        cx, cy, r = self.geometry(self.get_width(), self.get_height())
        best, dist = None, 26
        for i in range(len(self.labels)):
            lx, ly = polar(cx, cy, r, self.angle(i))
            d = math.hypot(lx - x, ly - y)
            if d < dist:
                best, dist = i, d
        if best is not None:
            self.user_set(best)

    def on_key(self, c, keyval, code, state):
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Right):
            self.user_set(self.value + 1)
        elif keyval in (Gdk.KEY_Down, Gdk.KEY_Left):
            self.user_set(self.value - 1)
        else:
            return False
        return True

    def draw(self, area, cr, w, h):
        cx, cy, r = self.geometry(w, h)
        layout = PangoCairo.create_layout(cr)
        for i, text in enumerate(self.labels):
            on = i == self.value
            layout.set_font_description(Pango.FontDescription.from_string(
                'Barlow Condensed SemiBold 10.5'))
            layout.set_text(text, -1)
            tw, th = layout.get_pixel_size()
            lx, ly = polar(cx, cy, r, self.angle(i))
            cr.set_source_rgba(*rgb('#ffcf73' if on else '#8f8879'))
            cr.move_to(lx - tw / 2, ly - th / 2)
            PangoCairo.show_layout(cr, layout)
            # position dot
            dx, dy = polar(cx, cy, r - 22, self.angle(i))
            cr.set_source_rgba(*rgb('#ffbf4d' if on else '#5a554c'))
            cr.arc(dx, dy, 2.2 if on else 1.6, 0, 2 * math.pi)
            cr.fill()

        body = 24
        shadow(cr, cx, cy, body, 5, 0.6)
        g = cairo.RadialGradient(cx - 8, cy - 9, 2, cx, cy, body)
        g.add_color_stop_rgba(0, *rgb('#3d3d3d'))
        g.add_color_stop_rgba(1, *rgb('#0d0d0d'))
        cr.set_source(g)
        cr.arc(cx, cy, body, 0, 2 * math.pi)
        cr.fill()

        # chicken-head bar
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(math.radians(self.angle(self.value)))
        bw, top, bottom = 14, -38, 13
        g = cairo.LinearGradient(-bw / 2, 0, bw / 2, 0)
        for off, col in ((0, '#121212'), (0.45, '#333333'), (1, '#101010')):
            g.add_color_stop_rgba(off, *rgb(col))
        cr.set_source(g)
        rr = bw / 2
        cr.new_sub_path()
        cr.arc(0, top + rr, rr, math.pi, 0)
        cr.line_to(rr, bottom)
        cr.arc(0, bottom, rr, 0, math.pi)
        cr.close_path()
        cr.fill()
        cr.set_source_rgba(*rgb('#f2ead8'))
        cr.set_line_width(2.2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(0, top + 4)
        cr.line_to(0, top + 18)
        cr.stroke()
        cr.restore()

        if self.has_focus():
            cr.set_source_rgba(*rgb('#e7a83e', 0.9))
            cr.set_line_width(2)
            cr.arc(cx, cy, body + 6, 0, 2 * math.pi)
            cr.stroke()


def led(on=False):
    box = Gtk.Box(valign=Gtk.Align.CENTER)
    box.add_css_class('led')
    if on:
        box.add_css_class('on')
    return box


def set_led(box, on):
    (box.add_css_class if on else box.remove_css_class)('on')
