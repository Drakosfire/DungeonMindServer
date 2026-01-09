# Fantasy Fonts for Backend Export

Download TTF versions of these fonts from Google Fonts and place them in this directory.
Pillow uses TTF files for server-side text rendering during export.

## Required Fonts

| Font | Download Link |
|------|---------------|
| MedievalSharp | https://fonts.google.com/specimen/MedievalSharp |
| Pirata One | https://fonts.google.com/specimen/Pirata+One |
| Uncial Antiqua | https://fonts.google.com/specimen/Uncial+Antiqua |
| Cinzel | https://fonts.google.com/specimen/Cinzel |
| IM Fell English | https://fonts.google.com/specimen/IM+Fell+English |

## Expected Files

After downloading, rename files to match these names:
- `MedievalSharp-Regular.ttf`
- `PirataOne-Regular.ttf`
- `UncialAntiqua-Regular.ttf`
- `Cinzel-Regular.ttf`
- `IMFellEnglish-Regular.ttf`

## Usage

These fonts are loaded by `/mapgenerator/compositing.py` using Pillow's `ImageFont.truetype()`.

## License

All fonts are licensed under the Open Font License (OFL).
