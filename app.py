#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image2SVG - Convertisseur d'images vers SVG + Visionneuse SVG
Formats supportés en entrée : PNG, JPG, JPEG, BMP, GIF, WEBP, TIFF, ICO
Deux modes de conversion :
  - Vectorisation (vtracer) : vrai SVG vectoriel
  - Encapsulation (base64)  : l'image est intégrée telle quelle dans un SVG
"""

import os
import sys
import base64
import mimetypes
import traceback

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon, QPainter, QWheelEvent
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QListWidget, QComboBox,
    QProgressBar, QMessageBox, QScrollArea, QTabWidget, QSlider,
    QCheckBox, QGroupBox
)

try:
    import vtracer
    HAS_VTRACER = True
except Exception:
    HAS_VTRACER = False

from PIL import Image

SUPPORTED = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".ico")


# ----------------------------------------------------------------------
# Conversion
# ----------------------------------------------------------------------
def convert_embed(src: str, dst: str) -> None:
    """Encapsule l'image en base64 dans un fichier SVG (fidélité parfaite)."""
    img = Image.open(src)
    w, h = img.size
    # Convertir en PNG pour un rendu universel
    from io import BytesIO
    buf = BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'  <image width="{w}" height="{h}" '
        f'xlink:href="data:image/png;base64,{data}"/>\n'
        f'</svg>\n'
    )
    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg)


def convert_vectorize(src: str, dst: str, colormode: str = "color") -> None:
    """Vectorisation réelle avec vtracer."""
    if not HAS_VTRACER:
        raise RuntimeError("vtracer n'est pas installé")
    # vtracer préfère les PNG : conversion préalable si besoin
    tmp = None
    if not src.lower().endswith(".png"):
        from tempfile import NamedTemporaryFile
        t = NamedTemporaryFile(suffix=".png", delete=False)
        tmp = t.name
        t.close()
        Image.open(src).convert("RGBA").save(tmp, format="PNG")
        src = tmp
    try:
        vtracer.convert_image_to_svg_py(
            src, dst,
            colormode=colormode,        # "color" ou "binary"
            hierarchical="stacked",
            mode="spline",
            filter_speckle=4,
            color_precision=6,
            layer_difference=16,
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3,
        )
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ----------------------------------------------------------------------
# Visionneuse SVG avec zoom
# ----------------------------------------------------------------------
class SvgViewer(QScrollArea):
    def __init__(self):
        super().__init__()
        self.svg = QSvgWidget()
        self.svg.setStyleSheet("background: white;")
        self.setWidget(self.svg)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.zoom = 1.0
        self.base_size = QSize(0, 0)
        self.current_file = None

    def load(self, path: str):
        self.svg.load(path)
        self.current_file = path
        size = self.svg.renderer().defaultSize()
        if not size.isValid() or size.width() <= 0:
            size = QSize(600, 600)
        self.base_size = size
        self.zoom = 1.0
        self.apply_zoom()

    def apply_zoom(self):
        w = max(1, int(self.base_size.width() * self.zoom))
        h = max(1, int(self.base_size.height() * self.zoom))
        self.svg.setFixedSize(w, h)

    def set_zoom(self, factor: float):
        self.zoom = max(0.05, min(20.0, factor))
        self.apply_zoom()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            self.set_zoom(self.zoom * (1.15 if delta > 0 else 1 / 1.15))
            event.accept()
        else:
            super().wheelEvent(event)


# ----------------------------------------------------------------------
# Fenêtre principale
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image2SVG - Convertisseur & Visionneuse SVG")
        self.resize(1000, 700)

        tabs = QTabWidget()
        tabs.addTab(self.build_converter_tab(), "🔄 Convertisseur")
        tabs.addTab(self.build_viewer_tab(), "👁 Visionneuse SVG")
        self.setCentralWidget(tabs)

    # ---------------- Onglet convertisseur ----------------
    def build_converter_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel(
            "Formats acceptés : PNG, JPG, BMP, GIF, WEBP, TIFF, ICO\n"
            "Astuce : la vectorisation convient aux logos/dessins, "
            "l'encapsulation aux photos."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Ajouter des images")
        btn_add.clicked.connect(self.add_files)
        btn_clear = QPushButton("🗑 Vider la liste")
        btn_clear.clicked.connect(lambda: self.file_list.clear())
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_clear)
        layout.addLayout(btn_row)

        self.file_list = QListWidget()
        layout.addWidget(self.file_list, stretch=1)

        opts = QGroupBox("Options de conversion")
        opts_layout = QHBoxLayout(opts)
        opts_layout.addWidget(QLabel("Mode :"))
        self.mode_combo = QComboBox()
        if HAS_VTRACER:
            self.mode_combo.addItem("Vectorisation couleur (vtracer)", "vec_color")
            self.mode_combo.addItem("Vectorisation noir & blanc (vtracer)", "vec_bw")
        self.mode_combo.addItem("Encapsulation base64 (fidélité exacte)", "embed")
        opts_layout.addWidget(self.mode_combo, stretch=1)
        layout.addWidget(opts)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_convert = QPushButton("🚀 Convertir en SVG")
        btn_convert.setMinimumHeight(40)
        btn_convert.clicked.connect(self.convert_all)
        layout.addWidget(btn_convert)

        self.status = QLabel("")
        layout.addWidget(self.status)
        return w

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.ico)"
        )
        for f in files:
            if f.lower().endswith(SUPPORTED):
                self.file_list.addItem(f)

    def convert_all(self):
        n = self.file_list.count()
        if n == 0:
            QMessageBox.information(self, "Info", "Ajoute d'abord des images.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if not out_dir:
            return

        mode = self.mode_combo.currentData()
        self.progress.setVisible(True)
        self.progress.setMaximum(n)
        ok, errors = 0, []

        for i in range(n):
            src = self.file_list.item(i).text()
            name = os.path.splitext(os.path.basename(src))[0] + ".svg"
            dst = os.path.join(out_dir, name)
            try:
                if mode == "vec_color":
                    convert_vectorize(src, dst, "color")
                elif mode == "vec_bw":
                    convert_vectorize(src, dst, "binary")
                else:
                    convert_embed(src, dst)
                ok += 1
            except Exception as e:
                errors.append(f"{os.path.basename(src)} : {e}")
            self.progress.setValue(i + 1)
            QApplication.processEvents()

        self.progress.setVisible(False)
        msg = f"✅ {ok}/{n} converties dans {out_dir}"
        if errors:
            msg += "\n⚠ Erreurs :\n" + "\n".join(errors[:5])
        self.status.setText(msg)
        QMessageBox.information(self, "Terminé", msg)

    # ---------------- Onglet visionneuse ----------------
    def build_viewer_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        btn_open = QPushButton("📂 Ouvrir un SVG")
        btn_open.clicked.connect(self.open_svg)
        btn_zoom_in = QPushButton("➕ Zoom")
        btn_zoom_in.clicked.connect(lambda: self.viewer.set_zoom(self.viewer.zoom * 1.25))
        btn_zoom_out = QPushButton("➖ Zoom")
        btn_zoom_out.clicked.connect(lambda: self.viewer.set_zoom(self.viewer.zoom / 1.25))
        btn_zoom_reset = QPushButton("1:1")
        btn_zoom_reset.clicked.connect(lambda: self.viewer.set_zoom(1.0))
        row.addWidget(btn_open)
        row.addStretch()
        row.addWidget(btn_zoom_out)
        row.addWidget(btn_zoom_reset)
        row.addWidget(btn_zoom_in)
        layout.addLayout(row)

        self.viewer = SvgViewer()
        layout.addWidget(self.viewer, stretch=1)

        self.viewer_status = QLabel("Astuce : Ctrl + molette pour zoomer")
        layout.addWidget(self.viewer_status)
        return w

    def open_svg(self):
        f, _ = QFileDialog.getOpenFileName(self, "Ouvrir un SVG", "", "SVG (*.svg)")
        if f:
            try:
                self.viewer.load(f)
                self.viewer_status.setText(f"📄 {f}")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
