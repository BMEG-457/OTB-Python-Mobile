"""Simple line+marker trend plot widget rendered via Kivy canvas."""

import numpy as np
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle, Ellipse, PushMatrix, PopMatrix, Rotate
from kivy.core.text import Label as CoreLabel
from kivy.metrics import sp


class TrendPlotWidget(Widget):
    """Canvas-based line+marker plot for discrete session data points.

    Usage::

        plot = TrendPlotWidget()
        plot.set_data(['2026-03-01', '2026-03-05'], [12.3, 14.1], 'Peak RMS')
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._x_labels = []
        self._y_values = []
        self._y_label = ''
        self.bind(pos=self._redraw, size=self._redraw)

    def set_data(self, x_labels, y_values, y_label=''):
        """Update the plot data and redraw.

        Args:
            x_labels: list of str (e.g. dates).
            y_values: list of float.
            y_label: str label for the y-axis.
        """
        self._x_labels = list(x_labels)
        self._y_values = list(y_values)
        self._y_label = y_label
        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        pad_l, pad_r, pad_b, pad_t = int(sp(60)), int(sp(15)), int(sp(40)), int(sp(20))
        plot_x = self.x + pad_l
        plot_y = self.y + pad_b
        plot_w = self.width - pad_l - pad_r
        plot_h = self.height - pad_b - pad_t

        with self.canvas:
            # Background
            Color(0.12, 0.12, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Plot area border
            Color(0.4, 0.4, 0.4, 1)
            Line(rectangle=(plot_x, plot_y, plot_w, plot_h), width=1)

        n = len(self._y_values)
        if n == 0:
            # Empty state label
            self._draw_text('No session data', self.center_x, self.center_y,
                            color=(0.5, 0.5, 0.5, 1), font_size=sp(14))
            return

        y_vals = np.array(self._y_values, dtype=float)
        y_min = float(y_vals.min())
        y_max = float(y_vals.max())
        if y_min == y_max:
            y_min -= 1
            y_max += 1
        y_range = y_max - y_min

        # Compute point positions
        if n == 1:
            xs_px = [plot_x + plot_w / 2]
        else:
            xs_px = [plot_x + i * plot_w / (n - 1) for i in range(n)]
        ys_px = [plot_y + (v - y_min) / y_range * plot_h for v in self._y_values]

        with self.canvas:
            # Grid lines (3 horizontal)
            Color(0.25, 0.25, 0.25, 1)
            for frac in (0.25, 0.5, 0.75):
                gy = plot_y + frac * plot_h
                Line(points=[plot_x, gy, plot_x + plot_w, gy], width=1)

            # Line connecting points
            if n > 1:
                Color(0.2, 0.7, 1.0, 1)
                pts = []
                for xp, yp in zip(xs_px, ys_px):
                    pts.extend([xp, yp])
                Line(points=pts, width=1.5)

            # Markers
            Color(0.3, 0.85, 0.5, 1)
            marker_r = 5
            for xp, yp in zip(xs_px, ys_px):
                Ellipse(pos=(xp - marker_r, yp - marker_r),
                        size=(marker_r * 2, marker_r * 2))

        # Y-axis labels (min, mid, max)
        for val, frac in [(y_min, 0), ((y_min + y_max) / 2, 0.5), (y_max, 1.0)]:
            ly = plot_y + frac * plot_h
            self._draw_text(f'{val:.1f}', plot_x - 8, ly,
                            anchor_x='right', font_size=sp(13))

        # X-axis labels (show first, last, and up to 3 in between)
        if n <= 5:
            show_indices = range(n)
        else:
            step = max(1, (n - 1) // 4)
            show_indices = list(range(0, n, step))
            if n - 1 not in show_indices:
                show_indices.append(n - 1)
        for i in show_indices:
            label = self._x_labels[i] if i < len(self._x_labels) else ''
            # Shorten date labels
            if len(label) > 5:
                label = label[5:]  # strip year prefix e.g. "2026-" -> "03-01"
            self._draw_text(label, xs_px[i], plot_y - 6,
                            anchor_y='top', font_size=sp(13))

        # Y-axis title (rotated 90° so it reads bottom-to-top)
        if self._y_label:
            label = CoreLabel(text=str(self._y_label), font_size=sp(14))
            label.refresh()
            tex = label.texture
            tw, th = tex.size
            cx = self.x + th / 2 + 4
            cy = plot_y + plot_h / 2
            with self.canvas:
                Color(0.7, 0.7, 0.7, 1)
                PushMatrix()
                Rotate(angle=90, origin=(cx, cy))
                Rectangle(texture=tex, pos=(cx - tw / 2, cy - th / 2), size=(tw, th))
                PopMatrix()

    def _draw_text(self, text, x, y, anchor_x='center', anchor_y='middle',
                   font_size=14, color=(0.8, 0.8, 0.8, 1)):
        """Render a text label on the canvas at (x, y)."""
        label = CoreLabel(text=str(text), font_size=font_size)
        label.refresh()
        tex = label.texture
        tw, th = tex.size
        if anchor_x == 'center':
            dx = x - tw / 2
        elif anchor_x == 'right':
            dx = x - tw
        else:
            dx = x
        if anchor_y == 'middle':
            dy = y - th / 2
        elif anchor_y == 'top':
            dy = y - th
        else:
            dy = y
        with self.canvas:
            Color(*color)
            Rectangle(texture=tex, pos=(dx, dy), size=tex.size)
