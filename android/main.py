#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image2SVG Android (Kivy)
Convertit PNG/JPG/BMP/GIF/WEBP/TIFF/ICO en SVG + visionneuse SVG.
Deux modes :
  - Image integree (base64) : fidelite exacte
  - Vectorisation simplifiee : vrais chemins vectoriels (blocs de couleur)
"""

import os
import re
import base64
from io import BytesIO

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.image import Image as KivyImage
from kivy.uix.scatter import Scatter
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock

from PIL import Image

SUPPORTED = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".ico")

# Permissions Android
try:
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path
    IS_ANDROID = True
except Exception:
    IS_ANDROID = False


def storage_root():
    if IS_ANDROID:
        try:
            return primary_external_storage_path()
        except Exception:
            return "/sdcard"
    return os.path.expanduser("~")


def output_dir():
    d = os.path.join(storage_root(), "Image2SVG")
    os.makedirs(d, exist_ok=True)
    return d


# ----------------------------------------------------------------------
# Conversion : image integree en base64
# ----------------------------------------------------------------------
def convert_embed(src, dst):
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    buf = BytesIO()
    img.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="%d" height="%d" viewBox="0 0 %d %d">\n'
        '  <image width="%d" height="%d" '
        'xlink:href="data:image/png;base64,%s"/>\n'
        '</svg>\n' % (w, h, w, h, w, h, data)
    )
    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg)


# ----------------------------------------------------------------------
# Conversion : vectorisation simplifiee (pur Python, sans dependance native)
# Quantification des couleurs puis fusion des pixels en rectangles vectoriels
# ----------------------------------------------------------------------
def convert_vector(src, dst, colors=12, max_side=320):
    img = Image.open(src).convert("RGB")
    ow, oh = img.size
    scale = 1.0
    if max(ow, oh) > max_side:
        scale = max_side / float(max(ow, oh))
        img = img.resize((max(1, int(ow * scale)), max(1, int(oh * scale))), Image.LANCZOS)
    w, h = img.size
    q = img.quantize(colors=colors, method=Image.MEDIANCUT)
    palette = q.getpalette()
    px = q.load()

    # 1) Runs horizontaux par ligne
    runs = {}  # index couleur -> liste de (x0, x1, y)
    for y in range(h):
        x = 0
        while x < w:
            c = px[x, y]
            x2 = x
            while x2 + 1 < w and px[x2 + 1, y] == c:
                x2 += 1
            runs.setdefault(c, []).append((x, x2, y))
            x = x2 + 1

    # 2) Fusion verticale des runs identiques en rectangles
    sx = ow / float(w)
    sy = oh / float(h)
    parts = []
    for c, lst in runs.items():
        r, g, b = palette[c * 3:c * 3 + 3]
        by_span = {}
        for x0, x1, y in lst:
            by_span.setdefault((x0, x1), []).append(y)
        d = []
        for (x0, x1), ys in by_span.items():
            ys.sort()
            start = prev = ys[0]
            for y in ys[1:] + [None]:
                if y is not None and y == prev + 1:
                    prev = y
                    continue
                X0 = round(x0 * sx, 2)
                Y0 = round(start * sy, 2)
                X1 = round((x1 + 1) * sx, 2)
                Y1 = round((prev + 1) * sy, 2)
                d.append("M%g %gH%gV%gH%gZ" % (X0, Y0, X1, Y1, X0))
                if y is not None:
                    start = prev = y
        if d:
            parts.append('  <path fill="#%02x%02x%02x" d="%s"/>' % (r, g, b, "".join(d)))

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" shape-rendering="crispEdges">\n%s\n</svg>\n'
        % (ow, oh, ow, oh, "\n".join(parts))
    )
    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg)


# ----------------------------------------------------------------------
# Selecteur de fichiers
# ----------------------------------------------------------------------
class FilePopup(Popup):
    def __init__(self, callback, filters, title="Choisir un fichier", **kw):
        super().__init__(title=title, size_hint=(0.95, 0.9), **kw)
        self.callback = callback
        box = BoxLayout(orientation="vertical", spacing=5, padding=5)
        self.chooser = FileChooserListView(path=storage_root(), filters=filters)
        box.add_widget(self.chooser)
        row = BoxLayout(size_hint_y=None, height=50, spacing=5)
        ok = Button(text="Valider")
        ok.bind(on_release=self.validate)
        cancel = Button(text="Annuler")
        cancel.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(cancel)
        row.add_widget(ok)
        box.add_widget(row)
        self.content = box

    def validate(self, *a):
        if self.chooser.selection:
            sel = self.chooser.selection[0]
            self.dismiss()
            self.callback(sel)


# ----------------------------------------------------------------------
# Onglet convertisseur
# ----------------------------------------------------------------------
class ConverterTab(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=8, padding=10, **kw)
        self.src = None

        self.add_widget(Label(
            text="Formats: PNG JPG BMP GIF WEBP TIFF ICO",
            size_hint_y=None, height=30))

        btn = Button(text="Choisir une image", size_hint_y=None, height=60)
        btn.bind(on_release=self.pick)
        self.add_widget(btn)

        self.lbl_src = Label(text="Aucune image selectionnee",
                             size_hint_y=None, height=60, text_size=(Window.width - 40, None),
                             halign="center", valign="middle")
        self.add_widget(self.lbl_src)

        self.preview = KivyImage(size_hint_y=1)
        self.add_widget(self.preview)

        self.mode = Spinner(
            text="Vectorisation simplifiee",
            values=("Vectorisation simplifiee", "Image integree (base64)"),
            size_hint_y=None, height=55)
        self.add_widget(self.mode)

        self.colors = Spinner(
            text="12 couleurs",
            values=("4 couleurs", "8 couleurs", "12 couleurs", "24 couleurs", "48 couleurs"),
            size_hint_y=None, height=55)
        self.add_widget(self.colors)

        conv = Button(text="CONVERTIR EN SVG", size_hint_y=None, height=70,
                      background_color=(0.2, 0.6, 0.9, 1))
        conv.bind(on_release=self.convert)
        self.add_widget(conv)

        self.status = Label(text="", size_hint_y=None, height=70,
                            text_size=(Window.width - 40, None),
                            halign="center", valign="middle")
        self.add_widget(self.status)

    def pick(self, *a):
        FilePopup(self.on_pick,
                  ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif",
                   "*.webp", "*.tif", "*.tiff", "*.ico",
                   "*.PNG", "*.JPG", "*.JPEG"],
                  "Choisir une image").open()

    def on_pick(self, path):
        self.src = path
        self.lbl_src.text = os.path.basename(path)
        try:
            self.preview.source = path
            self.preview.reload()
        except Exception:
            pass

    def convert(self, *a):
        if not self.src:
            self.status.text = "Choisis d'abord une image."
            return
        self.status.text = "Conversion en cours..."
        Clock.schedule_once(lambda dt: self._do_convert(), 0.1)

    def _do_convert(self):
        try:
            name = os.path.splitext(os.path.basename(self.src))[0] + ".svg"
            dst = os.path.join(output_dir(), name)
            if self.mode.text.startswith("Image"):
                convert_embed(self.src, dst)
            else:
                n = int(self.colors.text.split()[0])
                convert_vector(self.src, dst, colors=n)
            kb = os.path.getsize(dst) // 1024
            self.status.text = "OK -> %s (%d Ko)" % (dst, kb)
            app = App.get_running_app()
            app.viewer_tab.load_svg(dst)
        except Exception as e:
            self.status.text = "Erreur: %s" % e


# ----------------------------------------------------------------------
# Onglet visionneuse SVG (zoom / deplacement au doigt)
# ----------------------------------------------------------------------
class ViewerTab(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=8, padding=10, **kw)

        row = BoxLayout(size_hint_y=None, height=60, spacing=5)
        b_open = Button(text="Ouvrir un SVG")
        b_open.bind(on_release=self.pick)
        b_reset = Button(text="Recentrer")
        b_reset.bind(on_release=self.reset_view)
        row.add_widget(b_open)
        row.add_widget(b_reset)
        self.add_widget(row)

        self.zone = BoxLayout()
        self.scatter = Scatter(do_rotation=False, scale_min=0.1, scale_max=25)
        self.img = KivyImage(size_hint=(None, None), size=(600, 600))
        self.scatter.add_widget(self.img)
        self.zone.add_widget(self.scatter)
        self.add_widget(self.zone)

        self.info = Label(text="Pince a deux doigts pour zoomer",
                          size_hint_y=None, height=60,
                          text_size=(Window.width - 40, None),
                          halign="center", valign="middle")
        self.add_widget(self.info)

    def pick(self, *a):
        FilePopup(self.load_svg, ["*.svg", "*.SVG"], "Choisir un SVG").open()

    def load_svg(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m = re.search(r'base64,([A-Za-z0-9+/=\s]+)["\']', content)
            tmp = os.path.join(App.get_running_app().user_data_dir, "_preview.png")
            if m:
                # SVG a image integree : on decode le PNG
                raw = base64.b64decode(re.sub(r"\s", "", m.group(1)))
                with open(tmp, "wb") as f:
                    f.write(raw)
            else:
                # SVG vectoriel : rendu via les chemins
                self.render_paths(content, tmp)
            self.img.source = tmp
            self.img.reload()
            self.reset_view()
            self.info.text = os.path.basename(path)
        except Exception as e:
            self.info.text = "Erreur: %s" % e

    def render_paths(self, content, out_png):
        """Rendu des chemins rectangulaires generes par le convertisseur."""
        from PIL import ImageDraw
        mw = re.search(r'width="([\d.]+)"', content)
        mh = re.search(r'height="([\d.]+)"', content)
        W = int(float(mw.group(1))) if mw else 600
        H = int(float(mh.group(1))) if mh else 600
        sc = min(1.0, 1400.0 / max(W, H))
        im = Image.new("RGB", (max(1, int(W * sc)), max(1, int(H * sc))), "white")
        dr = ImageDraw.Draw(im)
        for fill, d in re.findall(r'<path fill="(#[0-9a-fA-F]{6})" d="([^"]+)"', content):
            col = tuple(int(fill[i:i + 2], 16) for i in (1, 3, 5))
            for x0, y0, x1, y1 in re.findall(
                    r'M([-\d.]+) ([-\d.]+)H([-\d.]+)V([-\d.]+)', d):
                dr.rectangle(
                    [float(x0) * sc, float(y0) * sc, float(x1) * sc, float(y1) * sc],
                    fill=col)
        im.save(out_png)

    def reset_view(self, *a):
        self.scatter.scale = 1
        self.scatter.pos = (0, 0)
        if self.img.texture:
            tw, th = self.img.texture.size
            zw, zh = self.zone.size
            if tw and th and zw and zh:
                k = min(zw / float(tw), zh / float(th))
                self.img.size = (tw * k, th * k)
                self.scatter.pos = (self.zone.x + (zw - tw * k) / 2,
                                    self.zone.y + (zh - th * k) / 2)


# ----------------------------------------------------------------------
class Image2SVGApp(App):
    title = "Image2SVG"

    def build(self):
        if IS_ANDROID:
            try:
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass
        panel = TabbedPanel(do_default_tab=False, tab_width=Window.width / 2)
        self.converter_tab = ConverterTab()
        self.viewer_tab = ViewerTab()
        t1 = TabbedPanelItem(text="Convertir")
        t1.add_widget(self.converter_tab)
        t2 = TabbedPanelItem(text="Visionneuse")
        t2.add_widget(self.viewer_tab)
        panel.add_widget(t1)
        panel.add_widget(t2)
        return panel


if __name__ == "__main__":
    Image2SVGApp().run()
