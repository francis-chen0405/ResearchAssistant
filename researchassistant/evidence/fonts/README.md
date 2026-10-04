# Embedded export font

`unifont-15.0.01.ttf` is the unmodified GNU Unifont 15.0.01 TrueType release,
from https://unifoundry.com/pub/unifont/unifont-15.0.01/font-builds/ .
The bundled `UNIFONT-LICENSE.txt` includes its SIL Open Font License 1.1 and
GPL with font embedding exception. This project uses the OFL option.

The exporter embeds a subset in each PDF and does not depend on system fonts.
Supported simple text includes Latin accents, typographic punctuation, Greek/math,
Cyrillic, Chinese, Japanese and Korean within the font's Basic Multilingual Plane.
Unsupported code points, control/private-use characters and scripts requiring
complex shaping raise a specific export error, preserving Markdown/DOCX access.
No replacement glyph is silently substituted. The original released text/hash
remain the export identity, independent of PDF font subsets and generation time.

Desktop packaging already includes the complete `researchassistant` data tree.
