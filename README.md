# Image2SVG 🖼️➡️📐

Convertisseur d'images (PNG, JPG, BMP, GIF, WEBP, TIFF, ICO) vers **SVG**, avec **visionneuse SVG** intégrée (zoom Ctrl+molette).

## Modes de conversion
- **Vectorisation couleur / N&B** (vtracer) : vrai SVG vectoriel, idéal pour logos et dessins
- **Encapsulation base64** : fidélité exacte, idéal pour photos

## Télécharger le .exe Windows
1. Onglet **Actions** du dépôt → dernier workflow vert → artefact `Image2SVG-Windows`
2. Ou onglet **Releases** → dernier build → `Image2SVG.exe`

## Lancer depuis les sources
```bash
pip install -r requirements.txt
python app.py
```

Le .exe est compilé automatiquement par GitHub Actions à chaque push sur `main`.
