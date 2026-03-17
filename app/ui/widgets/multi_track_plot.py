"""Multi-track stacked EMG plot widget rendered via Kivy canvas."""

import numpy as np
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Rectangle
from app.core import config as CFG


class MultiTrackPlotWidget(Widget):
    """Vertically stacked rolling plots — one track per aggregated signal.

    Each track has an independent circular buffer of length `display_samples`.
    Call update_track(idx, samples) to feed new data, then render() once per
    60fps tick to redraw all tracks.

    Performance notes vs original:
    - Per-track circular buffer with write-pointer replaces np.roll (no allocation)
    - xs shared and cached on size change (not recomputed each frame)
    - Per-track pts array pre-allocated; only ys filled each frame
    - .tolist() replaces list() for ~5x faster numpy→Python list conversion

    Args:
        track_labels: list of str — one label per track (determines track count).
        track_colors: optional list of (r,g,b,a) tuples; cycles through
                      CFG.MULTI_TRACK_COLORS if not supplied.
        display_samples: buffer length per track (default from config).
        downsample: render downsample factor (default from config).
    """

    def __init__(self, track_labels, track_colors=None,
                 display_samples=CFG.PLOT_DISPLAY_SAMPLES,
                 downsample=CFG.PLOT_DOWNSAMPLE, **kwargs):
        super().__init__(**kwargs)
        self._n      = len(track_labels)
        self._labels = track_labels
        self._display_samples = display_samples
        self._downsample = downsample
        self._n_pts = display_samples // downsample
        cap = display_samples

        # Per-track circular buffers and write-pointers (no np.roll on update)
        self._buffers    = [np.zeros(cap) for _ in range(self._n)]
        self._buf_writes = [0] * self._n

        # Pre-allocated linearisation scratch buffers (one per track)
        self._render_bufs = [np.empty(cap) for _ in range(self._n)]

        # Pre-allocated interleaved point arrays [x0,y0, x1,y1, ...] per track
        self._pts_arrays = [np.empty(2 * self._n_pts) for _ in range(self._n)]

        # Peak-hold y-axis range per track — only expands, never shrinks
        self._y_mins = [0.0] * self._n
        self._y_maxs = [0.0] * self._n

        # Shared xs — computed once on size change, stored in pts[0::2]
        self._xs_valid = False

        palette        = track_colors or CFG.MULTI_TRACK_COLORS
        self._colors   = [palette[i % len(palette)] for i in range(self._n)]

        # Pre-allocate canvas instructions: background rect + line per track
        self._rects = []
        self._lines = []
        with self.canvas:
            for i in range(self._n):
                Color(*CFG.PLOT_BG_RGBA)
                self._rects.append(Rectangle(pos=self.pos, size=self.size))
                Color(*self._colors[i])
                self._lines.append(Line(points=[], width=1))

        self.bind(pos=self._update_layout, size=self._update_layout)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _update_layout(self, *args):
        if self.width == 0:
            return
        # Recompute shared xs and cache into each track's pts[0::2]
        xs = self.x + np.arange(self._n_pts) * (self.width / max(self._n_pts - 1, 1))
        for pts in self._pts_arrays:
            pts[0::2] = xs
        self._xs_valid = True
        self.render()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_track(self, idx, samples):
        """Write new samples into one track's circular buffer.

        Args:
            idx:     track index (0-based).
            samples: 1-D np.ndarray of new samples.
        """
        if idx < 0 or idx >= self._n:
            return

        new = samples
        n   = len(new)
        cap = self._display_samples
        w   = self._buf_writes[idx]
        end = w + n

        if n >= cap:
            self._buffers[idx][:] = new[-cap:]
            self._buf_writes[idx]  = 0
        elif end <= cap:
            self._buffers[idx][w:end] = new
            self._buf_writes[idx]     = end % cap
        else:
            split = cap - w
            self._buffers[idx][w:]     = new[:split]
            self._buffers[idx][:n - split] = new[split:]
            self._buf_writes[idx]          = n - split

    def reset_scale(self):
        """Reset peak-hold y-axis range for all tracks (call on stream start)."""
        for i in range(self._n):
            self._y_mins[i] = 0.0
            self._y_maxs[i] = 0.0

    def render(self):
        """Redraw all tracks. Call once per 60fps tick."""
        if not self._xs_valid or self.width == 0 or self.height == 0:
            return
        track_h = self.height / self._n
        for i in range(self._n):
            y_base = self.y + (self._n - 1 - i) * track_h
            self._rects[i].pos  = (self.x, y_base)
            self._rects[i].size = (self.width, track_h)
            self._draw_track(i, y_base, track_h)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _draw_track(self, idx, y_base, track_h):
        cap = self._display_samples
        w   = self._buf_writes[idx]
        buf = self._buffers[idx]
        rb  = self._render_bufs[idx]
        pts = self._pts_arrays[idx]

        # Linearise circular buffer into pre-allocated scratch (no allocation)
        rb[:cap - w] = buf[w:]
        rb[cap - w:] = buf[:w]

        ds = rb[::self._downsample]  # view, no copy

        # Expand peak-hold range (only grows, never shrinks)
        self._y_mins[idx] = min(self._y_mins[idx], ds.min())
        self._y_maxs[idx] = max(self._y_maxs[idx], ds.max())
        span = self._y_maxs[idx] - self._y_mins[idx]

        if span == 0:
            ys = np.full(self._n_pts, y_base + track_h * 0.5)
        else:
            ys = y_base + ((ds - self._y_mins[idx]) / span) * track_h * 0.8 + track_h * 0.1

        # Fill ys in-place; xs are already in pts[0::2] from _update_layout
        pts[1::2] = ys
        self._lines[idx].points = pts.tolist()
