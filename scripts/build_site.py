#!/usr/bin/env python3
"""
Builds the bird photo pages from one data file: assets/data/photos.json.

    python3 scripts/build_site.py

Generates (overwrites):
    gallery.html              overview of the bird groups (cover card per group)
    <group>.html              one page per bird group, photos grouped by species
    species.html              every species A-Z
    index.html                only the photo grid + nav; the rest of the page is hand-edited
and refreshes the top navigation menu on every other .html page.

Adding a photo:
    1. Put the image in assets/img/gallery/<species-slug>/ (new species: new folder, and add
       the slug to "species" in photos.json with its display name and group).
    2. Add an entry to "photos" in photos.json: {"file": "<species-slug>/<name>.jpg", "caption": "..."}
       Optional "crop": "12%" moves the 4:3 crop of a portrait photo toward the top.
    3. To feature it on the home page, add its file to the "home" list (order = display order).
    4. Run this script.
Images found in the folders but missing from photos.json are still published (caption =
species name) and reported, so nothing silently disappears.
"""
import datetime
import html
import json
import os
import re
import struct
import subprocess
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SITE, "assets/data/photos.json")
TEMPLATE = os.path.join(SITE, "scripts/templates/page.html")
GALLERY = "assets/img/gallery"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

# Pages whose nav highlights a given top-level menu item.
NAV_ACTIVE = {"index.html": "home", "about.html": "about", "catalog.html": "catalog",
              "durgapuja2025.html": "misc", "kumortuli2026.html": "misc",
              "durgapuja2026.html": "misc"}


def natural_key(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"^(.*?)(\d+)$", stem)
    return (m.group(1), int(m.group(2))) if m else (stem, -1)


def image_size(path):
    """(width, height) of a JPEG or PNG without third-party libraries."""
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        f.seek(2)
        while True:
            marker = f.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                raise ValueError(f"not a JPEG: {path}")
            length = struct.unpack(">H", f.read(2))[0]
            if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">xHH", f.read(5))
                return w, h
            f.seek(length - 2, 1)


def esc(text):
    """Escape &, <, > and double quotes (apostrophes are fine inside "..." attributes)."""
    return html.escape(text, quote=False).replace('"', "&quot;")


# ---------------------------------------------------------------- data
def load():
    data = json.load(open(DATA, encoding="utf-8"))
    groups = data["groups"]
    group_by_slug = {g["slug"]: g for g in groups}
    species = data["species"]
    problems, notes = [], []

    for slug, info in species.items():
        if info.get("group") not in group_by_slug:
            problems.append(f'species "{slug}" has unknown group "{info.get("group")}"')

    photos, seen = [], set()
    for p in data["photos"]:
        f = p["file"]
        if f in seen:
            problems.append(f"photo listed twice: {f}")
            continue
        seen.add(f)
        if not os.path.exists(os.path.join(SITE, GALLERY, f)):
            problems.append(f"photo file not found: {GALLERY}/{f}")
            continue
        photos.append(dict(p))

    # images on disk that photos.json doesn't know about yet
    for folder in sorted(os.listdir(os.path.join(SITE, GALLERY))):
        full = os.path.join(SITE, GALLERY, folder)
        if not os.path.isdir(full):
            continue
        for fn in sorted(os.listdir(full), key=natural_key):
            if fn.startswith(".") or not fn.lower().endswith(IMAGE_EXTS):
                continue
            f = f"{folder}/{fn}"
            if f not in seen:
                name = species.get(folder, {}).get("name", folder.replace("-", " ").title())
                photos.append({"file": f, "caption": name})
                seen.add(f)
                notes.append(f"not in photos.json, published with caption '{name}': {f}")

    for p in photos:
        slug = p["file"].split("/")[0]
        if slug not in species:
            problems.append(f'species folder "{slug}" missing from "species" in photos.json')
            continue
        p["species"] = slug
        w, h = image_size(os.path.join(SITE, GALLERY, p["file"]))
        p["portrait"] = h > w

    by_file = {p["file"]: p for p in photos}
    home = []
    for entry in data.get("home", []):
        f = entry if isinstance(entry, str) else entry["file"]
        if f not in by_file:
            problems.append(f"home list photo not in photos: {f}")
            continue
        home.append((by_file[f], isinstance(entry, dict) and entry.get("fill", False)))

    if problems:
        sys.exit("photos.json problems:\n  " + "\n  ".join(problems))
    return groups, species, photos, home, notes


# ---------------------------------------------------------------- html pieces
def nav(active):
    def cls(key):
        return ' class="active"' if key == active else ""
    return f'''      <nav id="navbar" class="navbar">
        <ul>
          <li><a href="index.html"{cls("home")}>Home</a></li>
          <li><a href="about.html"{cls("about")}>About</a></li>
          <li class="dropdown"><a href="#"{cls("gallery")}><span>Gallery</span> <i class="bi bi-chevron-down dropdown-indicator"></i></a>
            <ul>
              <li><a href="gallery.html">Bird Groups</a></li>
              <li><a href="species.html">All Species</a></li>
            </ul>
          </li>
          <li><a href="catalog.html"{cls("catalog")}>Catalog</a></li>
          <li class="dropdown"><a href="#"{cls("misc")}><span>Misc</span> <i class="bi bi-chevron-down dropdown-indicator"></i></a>
            <ul>
              <li><a href="durgapuja2025.html">Durga Puja 2025</a></li>
              <li><a href="kumortuli2026.html">Kumortuli 2026</a></li>
              <li><a href="durgapuja2026.html">Durga Puja 2026</a></li>
            </ul>
          </li>
        </ul>
      </nav><!-- .navbar -->'''


def tile(p, fill=False, crop_portraits=False):
    """One gallery card. crop_portraits: page shows portraits as 4:3 crops (uniform grid)."""
    src = f"{GALLERY}/{p['file']}"
    cap = esc(p["caption"])
    classes = ["gallery-item"]
    if p["portrait"]:
        classes.append("gallery-item--portrait")
    if fill:
        classes.append("gallery-item--fill")
    classes.append("h-100")
    style = ""
    if p["portrait"] and (fill or crop_portraits) and p.get("crop"):
        style = f' style="object-position: center {p["crop"]};"'
    return f'''          <div class="col-xl-3 col-lg-4 col-md-6">
            <div class="{' '.join(classes)}">
              <img src="{src}" class="img-fluid" alt="{esc(p['caption'])}"{style}>
              <div class="gallery-links d-flex align-items-center justify-content-center">
                <a href="{src}" title="{cap}" class="glightbox preview-link">
                  <p align="center">{cap}<br><br>
                    <i class="bi bi-arrows-angle-expand" align="center"></i>
                  </p>
                </a>
              </div>
            </div>
          </div>
'''


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def species_sections(slugs, species, photos_by_species, groups_by_slug=None):
    """Jump list + one section per species (uniform 4:3 grid)."""
    jump = ['    <!-- ======= Species Jump List ======= -->', '    <section class="species-jumplist">']
    for s in slugs:
        jump.append(f'          <a href="#{s}">{esc(species[s]["name"])} <span class="count">({len(photos_by_species[s])})</span></a>')
    jump.append("    </section>\n")
    out = ['    <!-- ======= Gallery Section ======= -->',
           '    <section id="gallery" class="gallery gallery--uniform">',
           '      <div class="container-fluid">', '']
    for s in slugs:
        ps = photos_by_species[s]
        group_link = ""
        if groups_by_slug:
            g = groups_by_slug[species[s]["group"]]
            group_link = f' <span class="species-group"><a href="{g["slug"]}.html">{esc(g["title"])}</a></span>'
        out.append(f'        <div class="species-section" id="{s}">')
        out.append(f'          <h3>{esc(species[s]["name"])} <span class="species-count">{plural(len(ps), "photo")}</span>{group_link}</h3>')
        out.append('          <div class="row gy-4 justify-content-center mb-4">')
        out.append("".join(tile(p, crop_portraits=True) for p in ps).rstrip("\n"))
        out.append("          </div>")
        out.append("        </div>")
        out.append("")
    return "\n".join(jump), out


def page(title, hero_title, hero_text, content, active="gallery"):
    t = open(TEMPLATE, encoding="utf-8").read()
    hero = f"            <h2>{esc(hero_title)}</h2>\n            <p>{hero_text}</p>\n"
    return (t.replace("{{TITLE}}", esc(title)).replace("{{NAV}}", nav(active))
             .replace("{{HERO}}", hero).replace("{{CONTENT}}", content))


def write(name, text):
    path = os.path.join(SITE, name)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    if old != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return old != text


# ---------------------------------------------------------------- pages
def build_group_pages(groups, species, photos_by_species):
    built = []
    for i, g in enumerate(groups):
        slugs = sorted((s for s in species if species[s]["group"] == g["slug"] and photos_by_species.get(s)),
                       key=lambda s: species[s]["name"].lower())
        n = sum(len(photos_by_species[s]) for s in slugs)
        jump, out = species_sections(slugs, species, photos_by_species)
        prev_g, next_g = groups[i - 1], groups[(i + 1) % len(groups)]
        out.append(f'''        <div class="text-center pb-4" style="font-size: 14px;">
          <a href="{prev_g["slug"]}.html">&larr; {esc(prev_g["title"])}</a>
          &nbsp;&nbsp;|&nbsp;&nbsp;<a href="gallery.html">All bird groups</a>&nbsp;&nbsp;|&nbsp;&nbsp;
          <a href="{next_g["slug"]}.html">{esc(next_g["title"])} &rarr;</a>
        </div>
''')
        out.append("      </div>\n    </section><!-- End Gallery Section -->")
        text = f'{esc(g["blurb"])} {plural(len(slugs), "species").replace("speciess", "species")}, {plural(n, "photo")}.'
        write(f'{g["slug"]}.html', page(g["title"], g["title"], text, jump + "\n" + "\n".join(out)))
        built.append((g, slugs, n))
    return built


def build_overview(built, home_files):
    cards = []
    for g, slugs, n in built:
        cover = g.get("cover")
        if not cover:
            group_photos = [p for s in slugs for p in photos_by_species_global[s]]
            landscapes = [p for p in group_photos if not p["portrait"]]
            featured = [p for p in landscapes if p["file"] in home_files]
            cover = (featured or landscapes or group_photos)[0]["file"]
        cards.append(f'''          <div class="col-xl-4 col-md-6">
            <a href="{g["slug"]}.html" class="group-card">
              <img src="{GALLERY}/{cover}" alt="{esc(g["title"])}" loading="lazy">
              <div class="group-card-text">
                <h3>{esc(g["title"])}</h3>
                <p>{esc(g["blurb"])}</p>
                <span class="group-card-count">{plural(len(slugs), "species").replace("speciess", "species")} &middot; {plural(n, "photo")}</span>
              </div>
            </a>
          </div>
''')
    content = ('    <!-- ======= Gallery Section ======= -->\n'
               '    <section id="gallery" class="gallery">\n'
               '      <div class="container-fluid">\n\n'
               '        <div class="row gy-4 justify-content-center">\n\n'
               + "".join(cards) +
               '\n        </div>\n\n'
               '        <p class="text-center pt-4" style="font-size: 14px;">Looking for a particular bird? '
               'See <a href="species.html">all species A&ndash;Z</a>.</p>\n\n'
               '      </div>\n    </section><!-- End Gallery Section -->')
    total = sum(n for _, _, n in built)
    write("gallery.html", page("Gallery", "Gallery",
                               f"Our bird photos, grouped by kind of bird. {total} photos in {len(built)} groups.", content))


def build_species_page(groups, species, photos_by_species):
    slugs = sorted((s for s in species if photos_by_species.get(s)), key=lambda s: species[s]["name"].lower())
    n = sum(len(photos_by_species[s]) for s in slugs)
    jump, out = species_sections(slugs, species, photos_by_species, {g["slug"]: g for g in groups})
    out.append("      </div>\n    </section><!-- End Gallery Section -->")
    write("species.html", page("All Species", "All Species",
                               f'Every bird on the site, A&ndash;Z. {len(slugs)} species, {n} photos. '
                               f'Prefer browsing by kind of bird? See the <a href="gallery.html">bird groups</a>.',
                               jump + "\n" + "\n".join(out)))


def build_index(home):
    path = os.path.join(SITE, "index.html")
    s = open(path, encoding="utf-8").read()
    top = [tile(p, fill=fill) for p, fill in home if fill or not p["portrait"]]
    bottom = [tile(p) for p, fill in home if p["portrait"] and not fill]
    grid = ('        <div class="row gy-4 justify-content-center">\n\n' + "".join(top))
    if bottom:
        # an empty full-width .row inside the flex row forces the portraits onto a new line
        grid += '\n          <div class="row gy-4 justify-content-center"></div>\n' + "".join(bottom)
    grid += "\n        </div>\n"
    a = s.index('<section id="gallery"')
    b = s.index("</section><!-- End Gallery Section -->")
    section = s[a:b]
    keep = section[:section.index('<div class="container-fluid">') + len('<div class="container-fluid">')]
    keep = keep.replace('<section id="gallery" class="gallery">', '<section id="gallery" class="gallery gallery--home">')
    s = s[:a] + keep + "\n\n" + grid + "\n      </div>\n    " + s[b:]
    # styles now come from birds.css
    if "assets/css/birds.css" not in s:
        link = '<link href="assets/css/main.css?v=2" rel="stylesheet">\n'
        s = s.replace(link, link + '  <link href="assets/css/birds.css?v=1" rel="stylesheet">\n', 1)
    write("index.html", s)


# ---------------------------------------------------------------- page speed
# Grid tiles show a small thumbnail; the full photo only loads when it's opened
# in the lightbox (the <a href> keeps pointing at the original).
THUMB_DIR = "assets/img/thumbs"      # mirrors assets/img/: thumbs/gallery/..., thumbs/misc/...
THUMB_WIDTH = 720                    # ~2x a grid tile's on-screen width
THUMB_QUALITY = 62
MAIN_JS_VERSION = 3                  # bump when assets/js/main.js changes (cache-busting)
FADE_DELAY_MS = 700                  # page fade-in delay (data-aos-delay on <main>)
_size_cache = {}
thumb_stats = {"made": 0}


def size_of(rel):
    if rel not in _size_cache:
        _size_cache[rel] = image_size(os.path.join(SITE, rel))
    return _size_cache[rel]


def thumb_for(original):
    """Path of the thumbnail for assets/img/<x>, creating/refreshing it if needed."""
    rel = original[len("assets/img/"):]
    thumb = f"{THUMB_DIR}/{os.path.splitext(rel)[0]}.jpg"
    src_path, dst_path = os.path.join(SITE, original), os.path.join(SITE, thumb)
    if not os.path.exists(dst_path) or os.path.getmtime(dst_path) < os.path.getmtime(src_path):
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        w, _ = size_of(original)
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(THUMB_QUALITY)]
        if w > THUMB_WIDTH:
            cmd += ["--resampleWidth", str(THUMB_WIDTH)]
        subprocess.run(cmd + [src_path, "--out", dst_path], capture_output=True, check=True)
        thumb_stats["made"] += 1
    return thumb


IMG_TAG = re.compile(r'<img src="(assets/img/(?:thumbs/)?(?:gallery|misc)/[^"]+)"([^>]*)>')
TILE = re.compile(r'(<div class=")(gallery-item(?: [^"]*)?)(">\s*<img src="assets/img/(?:thumbs/)?((?:gallery|misc)/[^"]+)")')


def speed_up(s):
    """Thumbnails + lazy loading for photo <img>s, portrait tiles marked up front."""
    def original_of(src):
        if not src.startswith(THUMB_DIR + "/"):
            return src
        # thumbs are always .jpg; find the original whatever its extension
        base = "assets/img/" + os.path.splitext(src[len(THUMB_DIR) + 1:])[0]
        for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
            if os.path.exists(os.path.join(SITE, base + ext)):
                return base + ext
        return None

    def img(m):
        src, attrs = m.group(1), m.group(2)
        orig = original_of(src)
        if not orig or not os.path.exists(os.path.join(SITE, orig)):
            return m.group(0)                       # leave unknown/missing images alone
        if 'loading="' not in attrs:
            attrs += ' loading="lazy"'
        if 'decoding="' not in attrs:
            attrs += ' decoding="async"'
        return f'<img src="{thumb_for(orig)}"{attrs}>'

    def tile(m):
        classes, rel = m.group(2).split(), m.group(4)
        path = f"assets/img/{rel}"
        if not os.path.exists(os.path.join(SITE, path)):      # tile already points at a thumb
            path = original_of(f"{THUMB_DIR}/{rel}")
        if path and "gallery-item--portrait" not in classes:
            w, h = size_of(path)
            if h > w:
                classes.insert(1, "gallery-item--portrait")
        return m.group(1) + " ".join(classes) + m.group(3)

    s = TILE.sub(tile, s)
    s = IMG_TAG.sub(img, s)
    s = re.sub(r'src="assets/js/main\.js(?:\?v=\d+)?"', f'src="assets/js/main.js?v={MAIN_JS_VERSION}"', s)
    s = re.sub(r'(<main id="main" data-aos="fade" data-aos-delay=")\d+(")', rf"\g<1>{FADE_DELAY_MS}\2", s)
    s = re.sub(r'(<section id="hero"[^>]*data-aos-delay=")\d+(")', rf"\g<1>{FADE_DELAY_MS}\2", s)
    return s


def prune_thumbs():
    """Delete thumbnails whose original photo no longer exists."""
    removed = 0
    root = os.path.join(SITE, THUMB_DIR)
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            base = os.path.join(SITE, "assets/img", os.path.splitext(rel)[0])
            if not any(os.path.exists(base + e) for e in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")):
                os.remove(os.path.join(dirpath, fn))
                removed += 1
    return removed


def refresh_nav():
    """Update the menu, footer year and image loading (thumbnails/lazy) on every page."""
    for fn in sorted(os.listdir(SITE)):
        if not fn.endswith(".html"):
            continue
        path = os.path.join(SITE, fn)
        s = open(path, encoding="utf-8").read()
        if '<nav id="navbar"' not in s:
            continue
        a = s.index('      <nav id="navbar"') if '      <nav id="navbar"' in s else s.index('<nav id="navbar"')
        b = s.index("</nav><!-- .navbar -->") + len("</nav><!-- .navbar -->")
        s = s[:a] + nav(NAV_ACTIVE.get(fn, "gallery")) + s[b:]
        s = re.sub(r"Copyright 2020-\d{4} (<strong><span>Birder Couple</span></strong>\. All Rights Reserved)\.?",
                   rf"Copyright 2020-{datetime.date.today().year} \1.", s)
        write(fn, speed_up(s))


photos_by_species_global = {}


def main():
    groups, species, photos, home, notes = load()
    photos_by_species = {}
    for p in photos:
        photos_by_species.setdefault(p["species"], []).append(p)
    photos_by_species_global.update(photos_by_species)

    built = build_group_pages(groups, species, photos_by_species)
    build_overview(built, {p["file"] for p, _ in home})
    build_species_page(groups, species, photos_by_species)
    build_index(home)
    refresh_nav()

    print(f"Built gallery.html, species.html, index.html and {len(built)} group pages "
          f"({len(photos)} photos, {len(photos_by_species)} species, {len(home)} on the home page).")
    for g, slugs, n in built:
        print(f"  {g['slug']}.html: {len(slugs)} species, {n} photos")
    removed = prune_thumbs()
    print(f"Thumbnails: {thumb_stats['made']} created/updated" + (f", {removed} stale removed" if removed else ""))
    for n in notes:
        print("Note:", n)


if __name__ == "__main__":
    main()
