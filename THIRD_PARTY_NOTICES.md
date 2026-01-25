# Third-Party Notices

This project incorporates material from the projects listed below. The original copyright notices and licenses under which we received such materials are set out below.

---

## 1. Noto Serif CJK (思源宋体)

**Source**: https://github.com/notofonts/noto-cjk  
**License**: SIL Open Font License 1.1  
**Usage**: GUI display font (Chinese/Japanese/Korean text)  
**Distribution**: Font file bundled in `assets/fonts/`  
**License File**: `assets/fonts/OFL.txt`

### Copyright Notice

```
Copyright © 2014-2021 Adobe (http://www.adobe.com/).

Source Han Serif is a trademark of Adobe in the United States and/or other countries.
```

### License Text

```
SIL OPEN FONT LICENSE Version 1.1

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
http://scripts.sil.org/OFL

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.
```

---

## 2. vgmstream

**Source**: https://github.com/vgmstream/vgmstream  
**License**: ISC License  
**Usage**: Audio format conversion (`.wem` to `.wav`)  
**Distribution**: Binary files distributed separately (user download)  
**License File**: `tools/vgmstream/COPYING`

### License Text

```
Copyright (c) 2008-2025 Adam Gashlin, Fastelbja, Ronny Elfert, bnnm,
                        Christopher Snowhill, NicknineTheEagle, bxaimc,
                        Thealexbarney, CyberBotX, et al

Portions Copyright (c) 2004-2008, Marko Kreen
Portions Copyright 2001-2007  jagarl / Kazunori Ueno <jagarl@creator.club.ne.jp>
Portions Copyright (c) 1998, Justin Frankel/Nullsoft Inc.
Portions Copyright (C) 2006 Nullsoft, Inc.
Portions Copyright (c) 2005-2007 Paul Hsieh
Portions Copyright (C) 2000-2004 Leshade Entis, Entis-soft.
Portions Public Domain originating with Sun Microsystems

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

---

## 2. wwiser

**Source**: https://github.com/bnnm/wwiser  
**License**: MIT License  
**Usage**: Wwise `.bnk` file parsing  
**Distribution**: Included in repository (`tools/wwiser.pyz`)

### License Text

```
MIT License

Copyright (c) bnnm and contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 4. FModel (User Download Required)

**Source**: https://github.com/4sval/FModel  
**License**: GPL-3.0 License  
**Usage**: Game asset extraction  
**Distribution**: NOT included (GPL incompatibility) - users must download separately  
**Note**: FModel is an optional tool. Due to GPL-3.0 license incompatibility with our MIT license, we do not distribute FModel binaries. Users should download it from the official source.

### Why Not Included?

GPL-3.0 is a strong copyleft license. Including GPL-3.0 licensed binaries would require our entire project to adopt GPL-3.0, which conflicts with our MIT license. Therefore, we provide download instructions only.

---

## Python Dependencies

This project also uses various Python packages. Their licenses are listed in `pyproject.toml` and can be viewed with:

```bash
pip-licenses
```

Major dependencies include:
- **PyQt6**: GPL-3.0 / Commercial (application uses GPL-3.0 compatible code)
- **rapidfuzz**: MIT License
- **pytesseract**: Apache License 2.0
- **Pillow**: HPND License (PIL License)
- **mss**: MIT License

---

## License Compliance Summary

| Component | License | Compatibility | Distribution |
|-----------|---------|--------------|--------------|
| Ludiglot (main) | MIT | - | ✅ Distributed |
| vgmstream | ISC | ✅ Compatible | ⚠️ User download (license preserved) |
| wwiser | MIT | ✅ Compatible | ✅ Included |
| FModel | GPL-3.0 | ❌ Incompatible | ❌ User download only |
| PyQt6 | GPL-3.0 | ✅ Compatible* | ✅ pip install |

**Note**: PyQt6 GPL-3.0 is compatible because our application code is also GPL-3.0 compatible (MIT can be used in GPL projects).

---

## Acknowledgments

We thank all the developers and contributors of the above projects for their excellent work, which makes this project possible.

For questions about licensing, please open an issue on GitHub.
