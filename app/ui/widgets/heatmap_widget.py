"""8x8 HD-EMG heatmap widget rendered via Kivy canvas."""

import numpy as np
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line
from kivy.core.text import Label as CoreLabel
from app.core import config as CFG

# Colour used to fill dead-channel cells (distinct from both cold and hot).
_DEAD_CELL_RGB = (0.22, 0.20, 0.28)  # dark purple-grey


# channel_idx = col * 8 + (7 - row)  — column-major, bottom-left = ch0
def _channel_idx(col, row):
    return col * 8 + (7 - row)


class HeatmapWidget(Widget):
    """8x8 colour grid visualising per-channel RMS for the HD-EMG array.

    Call update(normalized_rms) with a (64,) array of values in [0, 1]
    to refresh the display. The widget pre-allocates all 64 canvas rectangles
    on construction; update() only changes their colours — no allocation at
    runtime.

    Channel layout follows the desktop convention:
        channel_idx = col * 8 + (7 - row)
        bottom-left = channel 0, column-major order.
    """

    COLS = CFG.HDSEMG_GRID_COLS
    ROWS = CFG.HDSEMG_GRID_ROWS

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._normalized_rms = np.zeros(CFG.HDSEMG_CHANNELS)
        self._cold = np.array(CFG.HEATMAP_COLD_RGB, dtype=float)
        self._hot  = np.array(CFG.HEATMAP_HOT_RGB,  dtype=float)
        self._dead_channels = CFG.DEAD_CHANNELS        # frozenset of 0-based logical indices
        self._heatmap_mode  = CFG.ADAPTER_HEATMAP_MODE # 'removed' | 'raw' | 'demo' | None

        # Pre-compute active channel indices for 'demo' mode averaging
        self._active_chs = np.array(
            [i for i in range(CFG.HDSEMG_CHANNELS) if i not in self._dead_channels],
            dtype=np.intp
        )

        # Pre-allocate 64 (Color + Rectangle) instruction pairs
        self._cell_colors = []   # list of Color instructions
        self._cell_rects  = []   # list of Rectangle instructions

        self._highlight_ch = None  # channel index being highlighted, or None

        with self.canvas:
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    c = Color(*(list(self._cold) + [1.0]))
                    r = Rectangle(pos=(0, 0), size=(1, 1))
                    self._cell_colors.append(c)
                    self._cell_rects.append(r)

            # Grid lines
            self._grid_color = Color(0.3, 0.3, 0.3, 1)
            self._grid_lines = []
            # Vertical lines (COLS - 1 inner + 2 outer = COLS + 1)
            for _ in range(self.COLS + 1):
                self._grid_lines.append(Line(points=[], width=1))
            # Horizontal lines (ROWS + 1)
            for _ in range(self.ROWS + 1):
                self._grid_lines.append(Line(points=[], width=1))

            # Channel number labels
            self._label_colors = []
            self._label_rects = []
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    lc = Color(1, 1, 1, 0.85)
                    lr = Rectangle(pos=(0, 0), size=(1, 1))
                    self._label_colors.append(lc)
                    self._label_rects.append(lr)

            # Dead-channel diagonal cross (×) overlays — only allocated in 'removed' mode
            self._dead_color = Color(*_DEAD_CELL_RGB, 1)
            self._dead_lines = []
            if self._heatmap_mode == 'removed':
                for _ in self._dead_channels:
                    self._dead_lines.append(Line(points=[], width=1.2))
                    self._dead_lines.append(Line(points=[], width=1.2))

            # Highlight overlay — drawn last so it renders on top
            self._highlight_color = Color(1, 1, 1, 0)  # white, alpha=0 (hidden)
            self._highlight_line = Line(ellipse=(0, 0, 1, 1), width=2)

        self._label_textures = [None] * (self.ROWS * self.COLS)
        # Pre-sort dead channels for stable line pairing in _update_layout
        self._dead_channels_sorted = sorted(self._dead_channels)
        self.bind(pos=self._update_layout, size=self._update_layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, normalized_rms):
        """Refresh cell colours from a (64,) array of values in [0, 1].

        Args:
            normalized_rms: np.ndarray shape (64,), clipped to [0, 1].
        """
        self._normalized_rms = np.clip(normalized_rms, 0.0, 1.0)
        self._redraw_colors()

    def set_highlight(self, channel_idx):
        """Highlight a cell with a white ellipse outline."""
        self._highlight_ch = channel_idx
        self._highlight_color.a = 1.0
        self._update_highlight_pos()

    def clear_highlight(self):
        """Remove the highlight."""
        self._highlight_ch = None
        self._highlight_color.a = 0.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_layout(self, *args):
        """Recompute cell positions and sizes when widget is resized/moved."""
        cell_w = self.width  / self.COLS
        cell_h = self.height / self.ROWS
        font_size = max(10, int(min(cell_w, cell_h) * 0.3))
        for row in range(self.ROWS):
            for col in range(self.COLS):
                idx = row * self.COLS + col
                x = self.x + col * cell_w
                # row 0 = top of grid (visually); row 7 = bottom
                y = self.y + (self.ROWS - 1 - row) * cell_h
                self._cell_rects[idx].pos  = (x, y)
                self._cell_rects[idx].size = (cell_w, cell_h)

                # Channel number label — "—" only in 'removed' mode for dead channels
                ch = _channel_idx(col, row)
                if ch in self._dead_channels and self._heatmap_mode == 'removed':
                    label_text = '\u2014'  # em dash
                    label_color = (0.5, 0.45, 0.6, 1)
                else:
                    label_text = str(ch + 1)
                    label_color = (1, 1, 1, 0.85)
                label = CoreLabel(text=label_text, font_size=font_size,
                                  color=label_color)
                label.refresh()
                tex = label.texture
                self._label_textures[idx] = tex
                self._label_rects[idx].texture = tex
                tw, th = tex.size
                self._label_rects[idx].size = (tw, th)
                self._label_rects[idx].pos = (x + (cell_w - tw) / 2,
                                              y + (cell_h - th) / 2)

        # Grid lines
        line_idx = 0
        # Vertical lines
        for c in range(self.COLS + 1):
            lx = self.x + c * cell_w
            self._grid_lines[line_idx].points = [lx, self.y, lx, self.y + self.height]
            line_idx += 1
        # Horizontal lines
        for r in range(self.ROWS + 1):
            ly = self.y + r * cell_h
            self._grid_lines[line_idx].points = [self.x, ly, self.x + self.width, ly]
            line_idx += 1

        # Dead-channel cross lines — only drawn in 'removed' mode
        if self._heatmap_mode == 'removed':
            pad = 4
            for i, ch in enumerate(self._dead_channels_sorted):
                col = ch // 8
                row = 7 - (ch % 8)
                x = self.x + col * cell_w
                y = self.y + (self.ROWS - 1 - row) * cell_h
                # top-left → bottom-right
                self._dead_lines[i * 2].points = [
                    x + pad, y + cell_h - pad, x + cell_w - pad, y + pad
                ]
                # top-right → bottom-left
                self._dead_lines[i * 2 + 1].points = [
                    x + cell_w - pad, y + cell_h - pad, x + pad, y + pad
                ]

        self._redraw_colors()
        self._update_highlight_pos()

    def _update_highlight_pos(self):
        """Position the highlight ellipse over the highlighted channel's cell."""
        if self._highlight_ch is None:
            return
        ch = self._highlight_ch
        # Reverse the channel_idx formula: ch = col * 8 + (7 - row)
        col = ch // 8
        row = 7 - (ch % 8)
        cell_w = self.width / self.COLS
        cell_h = self.height / self.ROWS
        x = self.x + col * cell_w
        y = self.y + (self.ROWS - 1 - row) * cell_h
        # Inset slightly so the ellipse fits within the cell
        pad = 2
        self._highlight_line.ellipse = (x + pad, y + pad,
                                        cell_w - 2 * pad, cell_h - 2 * pad)

    def _redraw_colors(self):
        """Update the RGBA of each Color instruction from _normalized_rms."""
        cold = self._cold
        hot  = self._hot
        dead_rgb = _DEAD_CELL_RGB
        mode = self._heatmap_mode

        # Pre-compute average of active channels once per frame for 'demo' mode
        if mode == 'demo' and len(self._active_chs):
            avg_active = float(np.mean(self._normalized_rms[self._active_chs]))
        else:
            avg_active = 0.0

        for row in range(self.ROWS):
            for col in range(self.COLS):
                ch  = _channel_idx(col, row)
                c   = self._cell_colors[row * self.COLS + col]
                if ch in self._dead_channels:
                    if mode == 'removed':
                        c.r, c.g, c.b, c.a = dead_rgb[0], dead_rgb[1], dead_rgb[2], 1.0
                    elif mode == 'demo':
                        rgb = cold + avg_active * (hot - cold)
                        c.r, c.g, c.b, c.a = float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0
                    else:  # 'raw' — render from normalized_rms (device sends 0, so always cold)
                        val = float(self._normalized_rms[ch]) if ch < CFG.HDSEMG_CHANNELS else 0.0
                        rgb = cold + val * (hot - cold)
                        c.r, c.g, c.b, c.a = float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0
                else:
                    val = float(self._normalized_rms[ch]) if ch < CFG.HDSEMG_CHANNELS else 0.0
                    rgb = cold + val * (hot - cold)
                    c.r, c.g, c.b, c.a = float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0
