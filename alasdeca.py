"""
canvas_app.py – Interactive canvas with draggable squares.

Customise the three hooks at the bottom of this file:
  • on_square_dropped(app, square_id)   – called after every drag-and-drop
  • solve(app)                           – called when the Solve button is pressed
  • parse_connectivity(raw)              – called with the raw text of the connectivity file
  • parse_data(raw)                      – called with the raw text of the data file

Solver dependency: PuLP  →  pip install pulp
"""

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json, math
# from PIL import Image, ImageTk


# ──────────────────────────────────────────────────────────────────────────────
#  Extended canvas for transparency
#  https://stackoverflow.com/questions/54637795/how-to-make-a-tkinter-canvas-rectangle-transparent
# ──────────────────────────────────────────────────────────────────────────────

# class TransparentCanvas(tk.Canvas):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self._images = []

#     def create_rectangle_alpha(self, x1, y1, x2, y2, **kwargs):
#         if 'alpha' in kwargs:
#             alpha = int(kwargs.pop('alpha') * 255)
#             fill = kwargs.pop('fill')
#             fill = tuple(int(x%255) for x in self.winfo_rgb(fill))
#             fill = fill + (alpha,)
#             image = Image.new('RGBA', (x2-x1, y2-y1), fill)
#             photo = ImageTk.PhotoImage(image)
#             self._images.append(photo)
#             self.create_image(x1, y1, image=photo, anchor='nw')
#         else:
#             super().create_rectangle(x1, y1, x2, y2, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
#  Square model
# ──────────────────────────────────────────────────────────────────────────────

class Square:
    """Represents one node on the canvas."""

    def __init__(self, sid: str, x: float, y: float, size: float = 60,
                 label: str = "", color: str = "#4A90D9"):
        self.sid   = sid        # unique string id
        self.x     = x          # centre x
        self.y     = y          # centre y
        self.size  = size       # half-width = size / 2
        self.label = label
        self.color = color
        self.data  = {}         # arbitrary payload loaded from data file

    # Canvas item ids (set by CanvasApp)
    rect_id  = None
    text_id  = None


# ──────────────────────────────────────────────────────────────────────────────
#  Main application
# ──────────────────────────────────────────────────────────────────────────────

class CanvasApp(tk.Tk):

    CANVAS_BG    = "#1E1E2E"
    SIDEBAR_BG   = "#16161F"
    EDGE_COLOR   = "#6C6F93"
    SELECT_COLOR = "#F4B942"
    GRAY_COLOR   = "#ACACAC"   # grayscale
    VORDER_COLOR = "#E06C75"   # vertical partial-order arcs
    HORDER_COLOR = "#56B6C2"   # horizontal partial-order arcs
    BTN_STYLE    = dict(font=("Consolas", 10, "bold"), relief="flat",
                        cursor="hand2", pady=8, padx=12)

    # ── zoom limits ───────────────────────────────────────────────────────────
    ZOOM_MIN = 0.05
    ZOOM_MAX = 10.0
    ZOOM_STEP = 1.15   # multiplicative step per scroll tick

    def __init__(self):
        super().__init__()
        self.title("Node Canvas")
        self.configure(bg=self.SIDEBAR_BG)
        self.minsize(900, 600)

        # World-space data
        self.squares:      dict[str, Square]    = {}
        self.connectivity: dict[str, list[str]] = {}

        # Viewport  (screen = world * zoom + pan)
        self._zoom:  float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0

        # Interaction state
        self._drag_data: dict       = {}
        self._pan_data:  dict       = {}
        self._selected:  str | None = None

        # UI flags
        self._autoupdate          = tk.BooleanVar(value=False)
        self._autoupdate_drag     = tk.BooleanVar(value=False)
        self._transitive_reduction = tk.BooleanVar(value=True)
        self._strong_setting      = tk.BooleanVar(value=False)
        self._draw_grayscale      = tk.BooleanVar(value=False)
        self._show_vorder         = tk.BooleanVar(value=False)

        self._show_horder         = tk.BooleanVar(value=False)

        self._last_computed = time.time()
        # self._ghost = None

        self._build_ui()
        self._add_demo_squares()

    # ── viewport helpers ──────────────────────────────────────────────────────

    def w2s(self, wx: float, wy: float) -> "tuple[float, float]":
        """World → screen."""
        return wx * self._zoom + self._pan_x, wy * self._zoom + self._pan_y

    def s2w(self, sx: float, sy: float) -> "tuple[float, float]":
        """Screen → world."""
        return (sx - self._pan_x) / self._zoom, (sy - self._pan_y) / self._zoom

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        sidebar = tk.Frame(self, bg=self.SIDEBAR_BG, width=240)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="NODE CANVAS", bg=self.SIDEBAR_BG,
                 fg="#A0A8D0", font=("Consolas", 11, "bold"),
                 pady=20).pack(fill=tk.X)

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=16)

        self._btn(sidebar, "📂  Load Topology",
                  self._load_connectivity, "#3A7BD5").pack(fill=tk.X, padx=16, pady=(16, 6))
        self._btn(sidebar, "📂  Load Data",
                  self._load_data,         "#3A7BD5").pack(fill=tk.X, padx=16, pady=(0, 6))
        self._btn(sidebar, "❌  Clear All",
                  self._clear_all_squares, "#3A7BD5").pack(fill=tk.X, padx=16, pady=(0, 6))

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=16, pady=8)

        self._btn(sidebar, "💾  Save Layout",
                  self._save_layout, "#2E7D52").pack(fill=tk.X, padx=16, pady=6)

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=16, pady=8)

        self._btn(sidebar, "⚡  Solve",
                  self._solve, "#B44D2E").pack(fill=tk.X, padx=16, pady=(6, 2))

        # Autoupdate checkbox
        tk.Checkbutton(
            sidebar, text="  Auto-update on drop",
            variable=self._autoupdate,
            bg=self.SIDEBAR_BG, fg="#A0A8D0",
            activebackground=self.SIDEBAR_BG, activeforeground="#A0A8D0",
            selectcolor="#2A2A3E",
            font=("Consolas", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, padx=20, pady=(0, 2))

        # Autoupdate on drag checkbox
        tk.Checkbutton(
            sidebar, text="  Auto-update while dragging",
            variable=self._autoupdate_drag,
            bg=self.SIDEBAR_BG, fg="#A0A8D0",
            activebackground=self.SIDEBAR_BG, activeforeground="#A0A8D0",
            selectcolor="#2A2A3E",
            font=("Consolas", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, padx=20, pady=(0, 2))

        # # Strong setting checkbox
        # tk.Checkbutton(
        #     sidebar, text="  Strong separation",
        #     variable=self._strong_setting,
        #     bg=self.SIDEBAR_BG, fg="#A0A8D0",
        #     activebackground=self.SIDEBAR_BG, activeforeground="#A0A8D0",
        #     selectcolor="#2A2A3E",
        #     font=("Consolas", 9), anchor="w", cursor="hand2",
        # ).pack(fill=tk.X, padx=20, pady=(0, 2))

        # Transitive reduction checkbox
        tk.Checkbutton(
            sidebar, text="  Transitive reduction",
            variable=self._transitive_reduction,
            bg=self.SIDEBAR_BG, fg="#A0A8D0",
            activebackground=self.SIDEBAR_BG, activeforeground="#A0A8D0",
            selectcolor="#2A2A3E",
            font=("Consolas", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, padx=20, pady=(0, 6))

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=16, pady=8)

        # Partial-order visualisation toggles
        tk.Label(sidebar, text="Drawing Options", bg=self.SIDEBAR_BG,
                 fg="#7A7FA8", font=("Consolas", 9, "bold")).pack(anchor="w", padx=20)

        # tk.Checkbutton(
        #     sidebar, text="  Grayscale",
        #     variable=self._draw_grayscale,
        #     command=self.redraw,
        #     bg=self.SIDEBAR_BG, fg=self.GRAY_COLOR,
        #     activebackground=self.SIDEBAR_BG, activeforeground=self.GRAY_COLOR,
        #     selectcolor="#2A2A3E",
        #     font=("Consolas", 9), anchor="w", cursor="hand2",
        # ).pack(fill=tk.X, padx=20, pady=(2, 0))

        tk.Checkbutton(
            sidebar, text="  Vertical order",
            variable=self._show_vorder,

            command=self.redraw,
            bg=self.SIDEBAR_BG, fg=self.VORDER_COLOR,
            activebackground=self.SIDEBAR_BG, activeforeground=self.VORDER_COLOR,
            selectcolor="#2A2A3E",
            font=("Consolas", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, padx=20, pady=(2, 0))

        tk.Checkbutton(
            sidebar, text="  Horizontal order",
            variable=self._show_horder,
            command=self.redraw,
            bg=self.SIDEBAR_BG, fg=self.HORDER_COLOR,
            activebackground=self.SIDEBAR_BG, activeforeground=self.HORDER_COLOR,
            selectcolor="#2A2A3E",
            font=("Consolas", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, padx=20, pady=(2, 6))

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=16, pady=8)

        # View controls
        self._btn(sidebar, "⊞  Fit to Canvas",
                  self._fit_to_canvas, "#4A5568").pack(fill=tk.X, padx=16, pady=6)

        ttk.Separator(sidebar, orient="horizontal").pack(fill=tk.X, padx=16, pady=8)

        # Info panel
        self._info_var = tk.StringVar(value="Click a square\nto inspect it.")
        tk.Label(sidebar, textvariable=self._info_var, bg=self.SIDEBAR_BG,
                 fg="#7A7FA8", font=("Consolas", 9), justify=tk.LEFT,
                 wraplength=175).pack(fill=tk.X, padx=16, pady=4)

        # Canvas
        self.canvas = tk.Canvas(self, bg=self.CANVAS_BG, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Left-button: drag squares
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # Middle-button or right-button: pan
        self.canvas.bind("<ButtonPress-2>",   self._on_pan_start)
        self.canvas.bind("<B2-Motion>",       self._on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self._on_pan_end)
        self.canvas.bind("<ButtonPress-3>",   self._on_pan_start)
        self.canvas.bind("<B3-Motion>",       self._on_pan_move)
        self.canvas.bind("<ButtonRelease-3>", self._on_pan_end)

        # Mouse-wheel: zoom
        self.canvas.bind("<MouseWheel>",      self._on_zoom)       # Windows / macOS
        self.canvas.bind("<Button-4>",        self._on_zoom)       # Linux scroll up
        self.canvas.bind("<Button-5>",        self._on_zoom)       # Linux scroll down

    def _btn(self, parent, text, cmd, bg):
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg="white",
                         activebackground=bg, activeforeground="white",
                         **self.BTN_STYLE)

    # ── Demo squares ──────────────────────────────────────────────────────────

    def _add_demo_squares(self):
        demo = [
            Square("A", 200, 150, 70,  "A", "#4A90D9"),
            Square("B", 400, 150, 170, "B", "#7B68EE"),
            Square("C", 300, 320, 80,  "C", "#50C878"),
            Square("D", 550, 300, 40,  "D", "#FF6B6B"),
        ]
        for sq in demo:
            self.squares[sq.sid] = sq
        self.connectivity = {"A": ["B", "C"], "B": ["C", "D"], "C": ["D"]}
        self.redraw()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def redraw(self):
        self.canvas.delete("all")
        if self._drag_data:
            self._draw_square(self._drag_data["sq"], is_ghost=True)
        for sq in self.squares.values():
            self._draw_square(sq)
        # Partial-order arcs drawn first (behind everything else)
        if self._show_vorder.get() or self._show_horder.get():

            self._draw_partial_orders()
        self._draw_edges()

    def _draw_edges(self):
        for src, targets in self.connectivity.items():
            if src not in self.squares:
                continue
            s = self.squares[src]
            sx, sy = self.w2s(s.x, s.y)
            for tgt in targets:
                if tgt not in self.squares:
                    continue
                t  = self.squares[tgt]
                tx, ty = self.w2s(t.x, t.y)
                self.canvas.create_line(
                    sx, sy, tx, ty,
                    fill=self.EDGE_COLOR, width=1.5,
                    dash=(6, 4), tags="edge"
                )
                #self._draw_arrowhead(sx, sy, tx, ty, self.EDGE_COLOR, size=8)

    def _draw_arrowhead(self, x1, y1, x2, y2, color, size=8):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        tip_x  = x2 - ux * 16
        tip_y  = y2 - uy * 16
        px, py = -uy * size * 0.5, ux * size * 0.5
        self.canvas.create_polygon(
            tip_x, tip_y,
            tip_x - ux * size + px, tip_y - uy * size + py,
            tip_x - ux * size - px, tip_y - uy * size - py,
            fill=color, outline="",
        )

    def _draw_square(self, sq: Square, gray: bool = False, transparent: bool = True, is_ghost: bool = False):
        sx, sy   = self.w2s(sq.x, sq.y)
        sh       = sq.size / 2 * self._zoom
        is_sel   = sq.sid == self._selected
        outline  = self.SELECT_COLOR if (is_sel and not is_ghost) else "#2A2A3E"
        width    = 3 if is_sel else 1
        alpha    = .5 if transparent else 1.0
        color    = "#ADADAD" if gray else sq.color

        # if not transparent:
        #     sq.rect_id = self.canvas.create_rectangle(
        #         sx - sh, sy - sh, sx + sh, sy + sh,
        #         fill=color, outline=outline, width=width,
        #         tags=("square", sq.sid),
        #     )
        # else:
        #     sq.rect_id = self.canvas.create_rectangle_alpha(
        #         sx - sh, sy - sh, sx + sh, sy + sh,
        #         fill=color, outline=outline, width=width,
        #         tags=("square", sq.sid), alpha=alpha
        #     )

        sq.rect_id = self.canvas.create_rectangle(
            sx - sh, sy - sh, sx + sh, sy + sh,
            fill=color, outline=outline, width=width,
            tags=("square", sq.sid),
        )
        
        font_size = max(6, int(11 * self._zoom))
        sq.text_id = self.canvas.create_text(
            sx, sy,
            text=sq.label or sq.sid,
            fill="white", font=("Consolas", font_size, "bold"),
            tags=("square_label", sq.sid),
        )

    # ── Partial-order visualisation ───────────────────────────────────────────

    def _draw_partial_orders(self):
        """Draw Bézier arcs for the current partial orders."""
        try:
            v_order, h_order = _infer_partial_orders(
                self.squares, self.connectivity,
                use_transitive_reduction=self._transitive_reduction.get(),
                use_stong_setting=app._strong_setting.get()
            )
        except Exception:
            return

        if self._show_vorder.get():

            for top, bot, _ in v_order:
                if top in self.squares and bot in self.squares:
                    self._draw_order_arc(
                        self.squares[top], self.squares[bot],
                        self.VORDER_COLOR, bend_x=0.15, bend_y=0.0,
                    )

        if self._show_horder.get():
            for lft, rgt, _ in h_order:
                if lft in self.squares and rgt in self.squares:
                    self._draw_order_arc(
                        self.squares[lft], self.squares[rgt],
                        self.HORDER_COLOR, bend_x=0.0, bend_y=0.15,
                    )

    def _draw_order_arc(self, sq_a: Square, sq_b: Square,
                        color: str, bend_x: float, bend_y: float):
        """
        Draw a cubic Bézier arc from sq_a to sq_b with a lateral bend.

        bend_x / bend_y control the perpendicular offset of the two
        control points (as a fraction of the centroid-to-centroid distance).
        The arc ends with an arrowhead at sq_b's centroid.
        """
        ax, ay = self.w2s(sq_a.x, sq_a.y)
        bx, by = self.w2s(sq_b.x, sq_b.y)

        dx, dy = bx - ax, by - ay
        # Perpendicular unit vector (rotated 90°)
        perp_x, perp_y = -dy, dx

        # Control points bent outward
        c1x = ax + dx * 0.33 + perp_x * bend_x
        c1y = ay + dy * 0.33 + perp_y * bend_x + perp_x * bend_y - perp_y * bend_y
        c2x = ax + dx * 0.67 + perp_x * bend_x
        c2y = ay + dy * 0.67 + perp_y * bend_x + perp_x * bend_y - perp_y * bend_y

        # Approximate Bézier with enough polyline segments for smoothness
        pts = []
        for i in range(21):
            t = i / 20
            u = 1 - t
            x = u**3*ax + 3*u**2*t*c1x + 3*u*t**2*c2x + t**3*bx
            y = u**3*ay + 3*u**2*t*c1y + 3*u*t**2*c2y + t**3*by
            pts.extend([x, y])

        self.canvas.create_line(*pts, fill=color, width=1.5,
                                smooth=False, tags="order_arc")
        # Arrowhead at the destination
        if len(pts) >= 4:
            self._draw_arrowhead(pts[-4], pts[-3], pts[-2], pts[-1],
                                 color, size=8)

    # ── Pan ───────────────────────────────────────────────────────────────────

    def _on_pan_start(self, event):
        self._pan_data = {"x": event.x, "y": event.y}

    def _on_pan_move(self, event):
        if not self._pan_data:
            return
        self._pan_x += event.x - self._pan_data["x"]
        self._pan_y += event.y - self._pan_data["y"]
        self._pan_data = {"x": event.x, "y": event.y}
        self.redraw()

    def _on_pan_end(self, event):
        self._pan_data = {}

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def _on_zoom(self, event):
        # Determine scroll direction (cross-platform)
        if event.num == 4 or event.delta > 0:
            factor = self.ZOOM_STEP
        else:
            factor = 1.0 / self.ZOOM_STEP

        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom * factor))
        if new_zoom == self._zoom:
            return

        # Zoom toward the mouse cursor
        self._pan_x = event.x - (event.x - self._pan_x) * (new_zoom / self._zoom)
        self._pan_y = event.y - (event.y - self._pan_y) * (new_zoom / self._zoom)
        self._zoom  = new_zoom
        self.redraw()

    # ── Fit to canvas ─────────────────────────────────────────────────────────

    def _fit_to_canvas(self):
        """Zoom and pan so all squares fill the canvas with padding."""
        if not self.squares:
            return

        self.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        PADDING = 60  # pixels of padding on each side

        xs = [sq.x for sq in self.squares.values()]
        ys = [sq.y for sq in self.squares.values()]
        half_sizes = [sq.size / 2 for sq in self.squares.values()]

        min_x = min(x - h for x, h in zip(xs, half_sizes))
        max_x = max(x + h for x, h in zip(xs, half_sizes))
        min_y = min(y - h for y, h in zip(ys, half_sizes))
        max_y = max(y + h for y, h in zip(ys, half_sizes))

        world_w = max_x - min_x or 1
        world_h = max_y - min_y or 1

        zoom = min((cw - 2 * PADDING) / world_w,
                   (ch - 2 * PADDING) / world_h)
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))

        # Centre the content
        self._zoom  = zoom
        self._pan_x = (cw - world_w * zoom) / 2 - min_x * zoom
        self._pan_y = (ch - world_h * zoom) / 2 - min_y * zoom
        self.redraw()

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def _hit_square(self, sx: float, sy: float) -> "Square | None":
        """Hit-test in screen space."""
        wx, wy = self.s2w(sx, sy)
        for sq in self.squares.values():
            h = sq.size / 2
            if sq.x - h <= wx <= sq.x + h and sq.y - h <= wy <= sq.y + h:
                return sq
        return None

    def _on_press(self, event):
        sq = self._hit_square(event.x, event.y)
        if sq:
            _ghost = Square("Ghost", sq.x, sq.y, sq.size,  sq.label, "#8A8A8B")
            directions = dict()
            for s in self.squares.values():
                direction = self._get_direction(s, _ghost)
                directions[s] = direction
            wx, wy = self.s2w(event.x, event.y)
            self._drag_data = {"sq": _ghost,
                               "original": sq,
                               "ox": wx - sq.x,
                               "oy": wy - sq.y,
                               "directions": directions}
            self._selected = sq.sid
            self._update_info(sq)
        else:
            self._selected = None
            self._info_var.set("Click a square\nto inspect it.")
        self.redraw()

    def _get_direction(self, sq: Square, target: Square):
        x_diff = sq.x - target.x
        y_diff = sq.y - target.y
        if abs(x_diff) > abs(y_diff):
            if x_diff > 0:
                return 0
            else:
                return 1
        else:
            if y_diff > 0:
                return 2
            else:
                return 3

    def _check_for_change(self, sq):
        directions = self._drag_data["directions"]
        for s in self.squares.values():
            direction = self._get_direction(s, sq)
            if directions[s] != direction:
                return True
        return False

    def _on_drag(self, event):
        if not self._drag_data:
            return
        sq = self._drag_data["sq"]
        wx, wy = self.s2w(event.x, event.y)
        sq.x = wx - self._drag_data["ox"]
        sq.y = wy - self._drag_data["oy"]
        if self._autoupdate_drag.get():
            if time.time() > self._last_computed + 0.02:
                # v_order, h_order = _infer_partial_orders(
                #     app.squares, app.connectivity,
                #     use_transitive_reduction=app._transitive_reduction.get(),
                #     use_stong_setting=app._strong_setting.get()
                # )
                if self._check_for_change(sq):
                    if self._drag_data:
                        sq = self._drag_data["sq"]
                        original = self._drag_data["original"]
                        original.x = sq.x
                        original.y = sq.y
                        # ── USER HOOK ─────────────────────────────────────────────────
                        new_pos = on_square_dropped(self, original.sid)
                        if new_pos:
                            original.x, original.y = new_pos
                        # ─────────────────────────────────────────────────────────────
                        solve(self)
                        self.redraw()
            self._last_computed = time.time()
        self.redraw()

    def _on_release(self, event):
        if self._drag_data:
            sq = self._drag_data["sq"]
            wx, wy = self.s2w(event.x, event.y)
            sq.x = wx - self._drag_data["ox"]
            sq.y = wy - self._drag_data["oy"]
            # ── USER HOOK ─────────────────────────────────────────────────
            new_pos = on_square_dropped(self, sq.sid, square=sq)
            if new_pos:
                original = self._drag_data["original"]
                original.x, original.y = new_pos
            # ─────────────────────────────────────────────────────────────
            if self._autoupdate.get() or self._autoupdate_drag.get():
                solve(self)
            self.redraw()
        self._drag_data = {}
        self.redraw()

    # ── Public helpers ────────────────────────────────────────────────────────

    def move_square(self, sid: str, x: float, y: float):
        """Programmatically move a square (world coordinates)."""
        if sid in self.squares:
            self.squares[sid].x = x
            self.squares[sid].y = y

    def resize_square(self, sid: str, size: float):
        if sid in self.squares:
            self.squares[sid].size = size

    def set_color(self, sid: str, color: str):
        if sid in self.squares:
            self.squares[sid].color = color

    def clear_square(self, sid: str):
        self.squares.pop(sid, None)
        self.redraw()

    def _clear_all_squares(self):
        self.squares = {}
        self.redraw()

    def add_square(self, sid: str, x: float, y: float,
                   size: float = 60, label: str = "", color: str = "#4A90D9"):
        sq = Square(sid, x, y, size, label, color)
        self.squares[sid] = sq
        self.redraw()
        return sq

    # ── Sidebar actions ───────────────────────────────────────────────────────

    def _load_connectivity(self):
        path = filedialog.askopenfilename(
            title="Load Connectivity",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path) as f:
                raw = f.read()
            self.connectivity = parse_connectivity(raw)
            self.redraw()
            messagebox.showinfo("Loaded", "Connectivity loaded successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load connectivity:\n{e}")

    def _load_data(self):
        path = filedialog.askopenfilename(
            title="Load Node Data",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path) as f:
                raw = f.read()
            result = parse_data(raw)
            for sid, props in result.items():
                if sid not in self.squares:
                    self.add_square(sid,
                                    props.get("x", 100),
                                    props.get("y", 100),
                                    props.get("size", 60),
                                    props.get("label", sid),
                                    props.get("color", "#4A90D9"))
                else:
                    sq = self.squares[sid]
                    if "x"     in props: sq.x     = props["x"]
                    if "y"     in props: sq.y     = props["y"]
                    if "size"  in props: sq.size  = props["size"]
                    if "label" in props: sq.label = props["label"]
                    if "color" in props: sq.color = props["color"]
                    sq.data = {k: v for k, v in props.items()
                               if k not in ("x", "y", "size", "label", "color")}
            self.redraw()
            messagebox.showinfo("Loaded", "Node data loaded successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load data:\n{e}")

    def _save_layout(self):
        path = filedialog.asksaveasfilename(
            title="Save Layout",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            layout = {
                "squares": {
                    sid: {"x": sq.x, "y": sq.y, "size": sq.size,
                          "label": sq.label, "color": sq.color, **sq.data}
                    for sid, sq in self.squares.items()
                },
                "connectivity": self.connectivity,
            }
            with open(path, "w") as f:
                json.dump(layout, f, indent=2)
            messagebox.showinfo("Saved", f"Layout saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save:\n{e}")

    def _solve(self):
        try:
            solve(self)
            self.redraw()
        except Exception as e:
            messagebox.showerror("Solve error", str(e))

    def _update_info(self, sq: Square):
        lines = [f"ID:    {sq.sid}",
                 f"Pos:   ({sq.x:.0f}, {sq.y:.0f})",
                 f"Size:  {sq.size:.0f}"]
        if sq.label:
            lines.insert(1, f"Label: {sq.label}")
        if sq.data:
            lines.append("── data ──")
            for k, v in sq.data.items():
                lines.append(f"{k}: {v}")
        self._info_var.set("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
#  USER-EDITABLE HOOKS  ← customise these to add your logic
# ══════════════════════════════════════════════════════════════════════════════

def on_square_dropped(app: CanvasApp, square_id: str, square: Square = None) -> "tuple[float,float] | None":
    """
    Called every time a square is released after dragging.

    Parameters
    ----------
    app       : the CanvasApp instance (access app.squares, app.connectivity, etc.)
    square_id : the sid of the square that was just dropped

    Returns
    -------
    (x, y) to override the drop position, or None to keep it where it landed.

    Example – snap to a 20-px grid:
        sq = app.squares[square_id]
        return round(sq.x / 20) * 20, round(sq.y / 20) * 20
    """
    if square is None:
        sq = app.squares[square_id]
    else:
        sq = square
    # ── snap to 20-px grid (change or remove as you like) ──
    GRID_SIZE = 5
    snapped_x = round(sq.x / GRID_SIZE) * GRID_SIZE
    snapped_y = round(sq.y / GRID_SIZE) * GRID_SIZE
    return snapped_x, snapped_y


# ──────────────────────────────────────────────────────────────────────────────
#  Solver helpers
# ──────────────────────────────────────────────────────────────────────────────

# Minimum gap (pixels) between non-adjacent square edges (paper: ε).
# Applied to primary separation constraints for non-adjacent pairs.
# Secondary (strong-setting) constraints always use gap = 0.
SEPARATION_MARGIN = 10

# Floating-point tolerance for the geometric separability test (gap >= 0).
_TOUCH_EPS = 1e-6


def _infer_partial_orders(
    squares:                 dict,
    connectivity:            dict,
    use_transitive_reduction: bool = True,
    use_stong_setting: bool = False,
) -> "tuple[list[tuple[str,str,float]], list[tuple[str,str,float]]]":
    """
    Step (a) – Infer vertical and horizontal partial orders (H, V) following
    Nickel et al. (TVCG 2022), Section 2.2.

    Every pair of squares is placed in at least one of the two orders.

    Weak setting (primary constraints)
    -----------------------------------
    For each pair compare |Δcx| vs |Δcy|:
      • |Δcx| >= |Δcy|  →  horizontal order H  (left/right)
      • |Δcy|  > |Δcx|  →  vertical order   V  (above/below)
    Direction is determined by geometric separability when the bounding boxes
    admit a separating line; centroid comparison is used as fallback.

    Strong setting (secondary constraints)
    ----------------------------------------
    For non-adjacent pairs whose bounding boxes admit *both* a horizontal and
    a vertical separating line, a secondary constraint is also added to the
    other order.  The paper sets gap = 0 for secondary constraints (they
    serve overlap-prevention, not visual separation).

    Gap values (paper Section 2.2)
    --------------------------------
    Each entry stores the numeric gap used in the LP separation constraint:
      • gap = 0              for adjacent pairs (allowed to touch)
      • gap = SEPARATION_MARGIN  for non-adjacent primary constraints
      • gap = 0              for non-adjacent secondary constraints

    Adjacency
    ----------
    A pair is *adjacent* when there is an undirected edge between them in the
    connectivity data (either direction).

    Transitive reduction
    ---------------------
    When use_transitive_reduction=True each order is pruned to its Hasse
    diagram.  When False all constraints (including redundant transitives)
    are kept, which may make the LP slower but produces identical solutions.

    Returns
    -------
    v_order : list of (top_sid, bot_sid, gap)   -- top is above  bot
    h_order : list of (lft_sid, rgt_sid, gap)   -- lft is left of rgt
    """
    # Build undirected adjacency set from directed connectivity data
    adjacent_pairs: set[frozenset] = set()
    for src, targets in connectivity.items():
        for tgt in targets:
            adjacent_pairs.add(frozenset({src, tgt}))

    v_order: list[tuple[str, str, float]] = []
    h_order: list[tuple[str, str, float]] = []

    ids = list(squares.keys())
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            sa = squares[ids[a]]
            sb = squares[ids[b]]
            ha, hb = sa.size / 2, sb.size / 2

            is_adjacent = frozenset({sa.sid, sb.sid}) in adjacent_pairs
            gap_primary   = 0.0 if is_adjacent else SEPARATION_MARGIN
            gap_secondary = 0.0   # paper: secondary constraints use gap = 0

            # ── geometric separability on each axis ───────────────────────
            # v_sep: True/direction if a horizontal line fits between boxes
            if sb.y - hb >= sa.y + ha - _TOUCH_EPS:
                v_dir = (sa.sid, sb.sid)   # a above b
            elif sa.y - ha >= sb.y + hb - _TOUCH_EPS:
                v_dir = (sb.sid, sa.sid)   # b above a
            else:
                v_dir = None               # boxes overlap vertically

            # h_sep: True/direction if a vertical line fits between boxes
            if sb.x - hb >= sa.x + ha - _TOUCH_EPS:
                h_dir = (sa.sid, sb.sid)   # a left of b
            elif sa.x - ha >= sb.x + hb - _TOUCH_EPS:
                h_dir = (sb.sid, sa.sid)   # b left of a
            else:
                h_dir = None               # boxes overlap horizontally

            # ── centroid-distance fallback direction ──────────────────────
            if v_dir is None:
                v_dir_fb = (sa.sid, sb.sid) if sa.y <= sb.y else (sb.sid, sa.sid)
            else:
                v_dir_fb = v_dir
            if h_dir is None:
                h_dir_fb = (sa.sid, sb.sid) if sa.x <= sb.x else (sb.sid, sa.sid)
            else:
                h_dir_fb = h_dir

            # ── weak setting: assign to dominant axis ─────────────────────
            use_vertical = abs(sa.y - sb.y) > abs(sa.x - sb.x)  # ties → horizontal

            if use_vertical:
                v_order.append((*v_dir_fb, gap_primary))
                # strong setting: non-adjacent pair also separable horizontally?
                if not is_adjacent and h_dir is not None and use_stong_setting:
                    h_order.append((*h_dir_fb, gap_secondary))
            else:
                h_order.append((*h_dir_fb, gap_primary))
                # strong setting: non-adjacent pair also separable vertically?
                if not is_adjacent and v_dir is not None and use_stong_setting:
                    v_order.append((*v_dir_fb, gap_secondary))

    # ── optional transitive reduction ────────────────────────────────────────
    if use_transitive_reduction:
        v_order = _transitive_reduction(v_order)
        h_order = _transitive_reduction(h_order)

    return v_order, h_order


def _transitive_reduction(
    order: "list[tuple[str,str,bool]]",
) -> "list[tuple[str,str,bool]]":
    """
    Remove transitive edges from a partial order given as a list of
    (lesser, greater, adjacent) tuples, returning the Hasse-diagram edges.

    An edge (u, v) is redundant if v is reachable from u via at least one
    other intermediate node, i.e. there exists w such that u < w and w
    (transitively) < v.  Such edges carry no additional information for the
    LP and are dropped.

    The adjacency flag of a retained edge is preserved unchanged.
    """
    if not order:
        return order

    # Collect all node ids that appear in this order
    nodes: set[str] = set()
    for u, v, _ in order:
        nodes.add(u)
        nodes.add(v)

    # Build successor sets (direct edges only, ignoring adjacency flag)
    from collections import defaultdict, deque
    successors: dict[str, set[str]] = defaultdict(set)
    for u, v, _ in order:
        successors[u].add(v)

    def reachable(start: str) -> set[str]:
        """BFS/DFS reachability from start (not including start itself)."""
        visited: set[str] = set()
        queue = deque(successors[start])
        while queue:
            node = queue.popleft()
            if node not in visited:
                visited.add(node)
                queue.extend(successors[node] - visited)
        return visited

    # An edge (u, v) is in the transitive reduction iff v is NOT reachable
    # from any other direct successor of u (i.e. not reachable from u
    # without using the direct u→v edge).
    reduced: list[tuple[str, str, bool]] = []
    for u, v, adj in order:
        # Reachability from u excluding the direct u→v edge
        other_successors = successors[u] - {v}
        indirectly_reachable: set[str] = set()
        for w in other_successors:
            indirectly_reachable.add(w)
            indirectly_reachable |= reachable(w)
        if v not in indirectly_reachable:
            reduced.append((u, v, adj))

    return reduced


def _build_and_solve_lp(
    squares:      dict,
    connectivity: dict,
    v_order:      list,
    h_order:      list,
    canvas_w:     float,
    canvas_h:     float,
) -> "dict[str, tuple[float, float]] | None":
    """
    Step (b) – Build and solve the LP following Nickel et al. (TVCG 2022),
    Section 3 (single-cartogram formulation).

    Notation (mirroring the paper)
    --------------------------------
    w_{rr'} = (size_r/2 + size_r'/2)  — sum of half-sizes (paper: (w(r)+w(r'))/2)
    T       — undirected set of connected (adjacent) region pairs
    H, V    — horizontal / vertical separation order lists, each entry (r, r', gap)

    Decision variables
    ------------------
    x_r, y_r        — centroid of square r  (bounded to canvas)
    h_{rr'}, v_{rr'} — non-negative excess distances (≥ 0) for r,r' ∈ T:
        h_{rr'} = max(|x_r - x_r'| - w_{rr'}, 0)   (horizontal box gap)
        v_{rr'} = max(|y_r - y_r'| - w_{rr'}, 0)   (vertical   box gap)

    Separation constraints  (paper eqs. 2–3)
    -----------------------------------------
    For each (r, r', gap) in H:   x_r' - x_r  >=  w_{rr'} + gap
    For each (r, r', gap) in V:   y_r' - y_r  >=  w_{rr'} + gap

      gap = 0              for adjacent (connected) pairs
      gap = SEPARATION_MARGIN  for non-adjacent primary constraints
      gap = 0              for non-adjacent secondary (strong-setting) constraints

    Distance constraints  (paper eqs. 4–6)
    ----------------------------------------
    For each {r, r'} ∈ T:
        h_{rr'}, v_{rr'} >= 0                       (eq. 4)
        h_{rr'} >= |x_r - x_r'| - w_{rr'}          (eq. 5, two linear inequalities)
        v_{rr'} >= |y_r - y_r'| - w_{rr'}          (eq. 6, two linear inequalities)

    The paper adds d_{rr'} = 0.25 * min(w(r), w(r')) to the RHS of eqs. 5–6
    to promote side-sharing over corner-only contact.

    Objective  (paper eq. 1)
    -------------------------
    min  Σ_{r,r' ∈ T}  ( h_{rr'} + v_{rr'} )

    This is the L1 sum of *box-gap excesses*: zero when squares touch or
    overlap, positive only when there is empty space between them.

    Canvas-boundary constraints
    ---------------------------
        x_r  ∈  [half_r,  canvas_w - half_r]
        y_r  ∈  [half_r,  canvas_h - half_r]

    Returns
    -------
    dict sid -> (x, y)  with optimal positions, or None if infeasible/error.
    """
    try:
        import pulp
    except ImportError:
        raise RuntimeError(
            "PuLP is not installed.\n"
            "Install it with:  pip install pulp"
        )

    prob = pulp.LpProblem("square_layout", pulp.LpMinimize)

    # ── centroid variables ───────────────────────────────────────────────────
    cx = {sid: pulp.LpVariable(f"cx_{sid}", lowBound=0) for sid in squares}
    cy = {sid: pulp.LpVariable(f"cy_{sid}", lowBound=0) for sid in squares}

    # ── canvas boundary constraints ──────────────────────────────────────────
    for sid, sq in squares.items():
        h = sq.size / 2
        prob += cx[sid] >= h,            f"bound_cx_lo_{sid}"
        prob += cy[sid] >= h,            f"bound_cy_lo_{sid}"
        prob += cx[sid] <= canvas_w - h, f"bound_cx_hi_{sid}"
        prob += cy[sid] <= canvas_h - h, f"bound_cy_hi_{sid}"

    # ── separation constraints (paper eqs. 2–3) ──────────────────────────────
    for idx, (top_sid, bot_sid, gap) in enumerate(v_order):
        if top_sid not in squares or bot_sid not in squares:
            continue
        w_rr = squares[top_sid].size / 2 + squares[bot_sid].size / 2
        prob += cy[bot_sid] - cy[top_sid] >= w_rr + gap, f"vsep_{idx}"

    for idx, (lft_sid, rgt_sid, gap) in enumerate(h_order):
        if lft_sid not in squares or rgt_sid not in squares:
            continue
        w_rr = squares[lft_sid].size / 2 + squares[rgt_sid].size / 2
        prob += cx[rgt_sid] - cx[lft_sid] >= w_rr + gap, f"hsep_{idx}"

    # ── collect undirected connected (adjacent) edge set T ───────────────────
    edges: set[tuple[str, str]] = set()
    for src, targets in connectivity.items():
        if src not in squares:
            continue
        for tgt in targets:
            if tgt not in squares or tgt == src:
                continue
            edges.add((min(src, tgt), max(src, tgt)))

    # ── distance variables h_{rr'}, v_{rr'}  (paper eqs. 4–6) ───────────────
    h_vars: dict[tuple, pulp.LpVariable] = {}
    v_vars: dict[tuple, pulp.LpVariable] = {}

    for (u, v) in edges:
        sq_u, sq_v = squares[u], squares[v]
        w_rr = sq_u.size / 2 + sq_v.size / 2

        # Paper's "improving adjacencies" correction (Section 3):
        # add d_{rr'} = 0.25 * min(size_r, size_r') to RHS of eqs. 5–6 so that
        # h = v = 0 is achievable when squares share a side segment of length d,
        # promoting side-sharing contact over corner-only touch.
        d_rr = 0.25 * min(sq_u.size, sq_v.size)

        tag = f"{u}_{v}"
        hv = pulp.LpVariable(f"h_{tag}", lowBound=0)
        vv = pulp.LpVariable(f"v_{tag}", lowBound=0)
        h_vars[(u, v)] = hv
        v_vars[(u, v)] = vv

        # eq. 5:  h_{rr'} >= |x_r - x_r'| - w_{rr'} + d_{rr'}
        prob += hv >= cx[u] - cx[v] - w_rr + d_rr, f"h_pos_{tag}"
        prob += hv >= cx[v] - cx[u] - w_rr + d_rr, f"h_neg_{tag}"

        # eq. 6:  v_{rr'} >= |y_r - y_r'| - w_{rr'} + d_{rr'}
        prob += vv >= cy[u] - cy[v] - w_rr + d_rr, f"v_pos_{tag}"
        prob += vv >= cy[v] - cy[u] - w_rr + d_rr, f"v_neg_{tag}"

    # ── objective: L1 sum of box-gap excesses (paper eq. 1) ─────────────────
    if edges:
        prob += pulp.lpSum(h_vars[e] + v_vars[e] for e in edges), "total_box_gap_L1"
    else:
        # No connected edges: minimise sum of coordinates for compact layout
        prob += pulp.lpSum(cx[sid] + cy[sid] for sid in squares), "compact"

    # ── solve ────────────────────────────────────────────────────────────────
    solver = pulp.PULP_CBC_CMD(msg=False)
    status = prob.solve(solver)

    if pulp.value(prob.objective) is None:
        return None  # infeasible or unbounded

    result: dict[str, tuple[float, float]] = {}
    for sid in squares:
        xv = pulp.value(cx[sid])
        yv = pulp.value(cy[sid])
        if xv is None or yv is None:
            return None
        result[sid] = (float(xv), float(yv))

    return result


def _apply_positions(
    squares: dict,
    positions: dict,
    canvas_w: float,
    canvas_h: float,
) -> None:
    """
    Step (c) – Write LP solution back into the Square objects.
    Clamps to canvas boundaries as a safety net.
    """
    for sid, (x, y) in positions.items():
        sq = squares[sid]
        h  = sq.size / 2
        sq.x = max(h, min(canvas_w - h, x))
        sq.y = max(h, min(canvas_h - h, y))


def solve(app: CanvasApp):
    """
    Layout solver hook – called when the Solve button is pressed.

    Implements the single-cartogram LP of Nickel et al. (TVCG 2022), Sec. 3.

    Pipeline
    --------
    (a) Infer H, V separation orders (weak + strong settings).
        Optionally apply transitive reduction (Hasse diagram).
    (b) Build and solve the LP:
          • Separation constraints enforce H, V with gap = ε for non-adjacent
            primary pairs and gap = 0 for adjacent / secondary pairs.
          • Objective: minimise Σ_{adjacent pairs} (h_{rr'} + v_{rr'})
            where h, v are the excess horizontal/vertical box-gap distances
            (L1 of box gaps, zero when squares touch — paper eq. 1).
    (c) Read optimal centroid coordinates and update the squares.

    Requires PuLP:  pip install pulp
    """
    if not app.squares:
        return

    w = app.canvas.winfo_width()  or 800
    h = app.canvas.winfo_height() or 600

    # ── (a) partial orders ───────────────────────────────────────────────────
    v_order, h_order = _infer_partial_orders(
        app.squares, app.connectivity,
        use_transitive_reduction=app._transitive_reduction.get(),
        use_stong_setting=app._strong_setting.get()
    )

    # ── (b) solve LP ─────────────────────────────────────────────────────────
    positions = _build_and_solve_lp(
        squares      = app.squares,
        connectivity = app.connectivity,
        v_order      = v_order,
        h_order      = h_order,
        canvas_w     = w,
        canvas_h     = h,
    )

    if positions is None:
        messagebox.showwarning(
            "Solve",
            "The LP was infeasible or could not be solved.\n"
            "Try moving squares so that more pairs are clearly separated "
            "along one axis, or increase the canvas size."
        )
        return

    # ── (c) apply positions ──────────────────────────────────────────────────
    _apply_positions(app.squares, positions, w, h)


def parse_connectivity(raw: str) -> dict:
    """
    Parse the text content of a connectivity file.
    Must return dict[str, list[str]]  (sid -> list of neighbour sids).

    Default: expects JSON like
        {"A": ["B", "C"], "B": ["C"]}
    """
    return json.loads(raw)


def parse_data(raw: str) -> dict:
    """
    Parse the text content of a node-data file.
    Must return dict[str, dict]  (sid -> property dict).

    Recognised property keys: x, y, size, label, color
    All other keys are stored in square.data for your own use.

    Default: expects JSON like
        {
          "A": {"x": 100, "y": 150, "size": 70, "label": "Alpha", "color": "#ff0000"},
          "B": {"x": 300, "y": 150}
        }
    """
    return json.loads(raw)


# ──────────────────────────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = CanvasApp()
    app.mainloop()


######## TODOS
# - Keep interacted region where it was dropped and move everything else
# - On click on a square visualize:
#   - all other regions it is adjacent to
#   - the constrianing regions (where are the LP constraints tight?)
# - Change Topology?