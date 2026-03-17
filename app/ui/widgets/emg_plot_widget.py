"""Real-time EMG plot widget rendered via Kivy canvas (no matplotlib)."""

import numpy as np
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle
from app.core import config as CFG


class EMGPlotWidget(Widget):
    """Rolling single-channel EMG plot.

    Displays the last `display_samples` samples of one channel,
    downsampled by `downsample` for performance.
    Call update(data) with a (channels, samples) array on each packet.

    Performance notes vs original:
    - Circular buffer with write-pointer replaces np.roll (no per-packet allocation)
    - xs array pre-computed on size change (not every frame)
    - pts array pre-allocated once; only ys filled each frame
    - .tolist() replaces list() for ~5x faster numpy→Python list conversion
    """

    def __init__(self, channel_index=CFG.PLOT_CHANNEL_INDEX,
                 display_samples=CFG.PLOT_DISPLAY_SAMPLES,
                 downsample=CFG.PLOT_DOWNSAMPLE, **kwargs):
        super().__init__(**kwargs)
        self.channel_index = channel_index
        self._display_samples = display_samples
        self._downsample = downsample
        self._n_pts = display_samples // downsample

        # Circular buffer — write-pointer avoids np.roll on every packet
        self._buffer    = np.zeros(display_samples)
        self._buf_write = 0

        # Pre-allocated render scratch buffer (linearised view of circular buf)
        self._render_buf = np.empty(display_samples)

        # Peak-hold y-axis range — only expands, never shrinks
        self._y_min = 0.0
        self._y_max = 0.0

        # Pre-allocated interleaved point array [x0,y0, x1,y1, ...]
        self._pts = np.empty(2 * self._n_pts)

        # xs cached from last size event; None forces recompute on first draw
        self._xs_valid = False

        with self.canvas:
            Color(*CFG.PLOT_BG_RGBA)
            self._rect = Rectangle(pos=self.pos, size=self.size)
            Color(*CFG.PLOT_LINE_RGBA)
            self._line = Line(points=[], width=1)

        self.bind(pos=self._update_layout, size=self._update_layout)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _update_layout(self, *args):
        self._rect.pos  = self.pos
        self._rect.size = self.size
        # Recompute xs and cache into pts[0::2]
        xs = self.x + np.arange(self._n_pts) * (self.width / max(self._n_pts - 1, 1))
        self._pts[0::2] = xs
        self._xs_valid  = True
        self._draw()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, data):
        """Write new samples into the circular buffer. No redraw — call render() separately.

        Args:
            data: np.ndarray shape (channels, samples).
        """
        if data.shape[0] <= self.channel_index:
            return

        new = data[self.channel_index]
        n   = len(new)
        cap = self._display_samples
        end = self._buf_write + n

        if n >= cap:
            # Incoming packet larger than entire buffer — just overwrite
            self._buffer[:] = new[-cap:]
            self._buf_write  = 0
        elif end <= cap:
            self._buffer[self._buf_write:end] = new
            self._buf_write = end % cap
        else:
            split = cap - self._buf_write
            self._buffer[self._buf_write:] = new[:split]
            self._buffer[:n - split]       = new[split:]
            self._buf_write = n - split

    def reset_scale(self):
        """Reset peak-hold y-axis range (call on stream start)."""
        self._y_min = 0.0
        self._y_max = 0.0

    def render(self):
        """Redraw the canvas from the current buffer. Call from the 60fps tick."""
        self._draw()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _draw(self):
        if not self._xs_valid or self.width == 0 or self.height == 0:
            self._line.points = []
            return

        # Linearise circular buffer into pre-allocated scratch (no allocation)
        idx = self._buf_write
        cap = self._display_samples
        self._render_buf[: cap - idx] = self._buffer[idx:]
        self._render_buf[cap - idx:]  = self._buffer[:idx]

        buf = self._render_buf[::self._downsample]  # view, no copy

        # Expand peak-hold range (only grows, never shrinks)
        self._y_min = min(self._y_min, buf.min())
        self._y_max = max(self._y_max, buf.max())
        span = self._y_max - self._y_min

        if span == 0:
            ys = np.full(self._n_pts, self.y + self.height * 0.5)
        else:
            ys = self.y + ((buf - self._y_min) / span) * self.height * 0.8 + self.height * 0.1

        # Fill ys in-place into pre-allocated pts array
        self._pts[1::2] = ys
        self._line.points = self._pts.tolist()
