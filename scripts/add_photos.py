#!/usr/bin/env python3
"""
Add new photos to the site in one step (macOS: uses the built-in `sips` and `mdls`).

    python3 scripts/add_photos.py PHOTO [PHOTO ...] --location "Rabindra Sarobar, Kolkata, India" [--home]

For each photo this:
  1. works out the species from the file name: greater_coucal8.jpg -> greater-coucal
     (trailing number dropped, underscores become hyphens);
  2. resizes it to 1600 px on the long edge and saves it in assets/img/gallery/<species>/
     (never overwrites an existing file);
  3. adds it to assets/data/photos.json with the caption "<Species>, <location>, <Mon YYYY>",
     taking the month/year from the photo's capture date;
  4. with --home, also features it at the top of the home page (portraits go to the
     portrait block at the bottom, shown uncropped);
  5. rebuilds the site (scripts/build_site.py).

New species: the first time a species appears, say which bird group it belongs to and,
if the name needs apostrophes or special capitalisation, its display name:

    python3 scripts/add_photos.py ~/Photos/blyth_paradise_flycatcher3.jpg \
        --location "Rabindra Sarobar, Kolkata, India" \
        --group songbirds --name "Blyth's Paradise Flycatcher"

Run with --dry-run to see what would happen without changing anything.
Captions, crops and the home-page order can be fine-tuned afterwards in photos.json
(then run: python3 scripts/build_site.py).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SITE, "assets/data/photos.json")
GALLERY = os.path.join(SITE, "assets/img/gallery")
LONG_EDGE = 1600
JPEG_QUALITY = 75   # keeps files around 300-500 KB at 1600 px


def slug_from_filename(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r"\d+$", "", stem).rstrip("_- ")
    return re.sub(r"[_\s]+", "-", base).lower()


def capture_month(path):
    """'Nov 2026' from the photo's capture date (Spotlight metadata), or None."""
    try:
        out = subprocess.run(["mdls", "-raw", "-name", "kMDItemContentCreationDate", path],
                             capture_output=True, text=True, check=True).stdout.strip()
        dt = datetime.datetime.strptime(out[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%b %Y")
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def pixel_size(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
                         capture_output=True, text=True, check=True).stdout
    w = int(re.search(r"pixelWidth: (\d+)", out).group(1))
    h = int(re.search(r"pixelHeight: (\d+)", out).group(1))
    return w, h


def main():
    ap = argparse.ArgumentParser(description="Add photos to the site and rebuild it.")
    ap.add_argument("photos", nargs="+", help="image files to add (named like greater_coucal8.jpg)")
    ap.add_argument("--location", help='place for the caption, e.g. "Rabindra Sarobar, Kolkata, India"')
    ap.add_argument("--home", action="store_true", help="also feature the photos on the home page")
    ap.add_argument("--group", help="bird group for a NEW species (e.g. songbirds, raptors)")
    ap.add_argument("--name", help="display name for a NEW species (default: from the file name)")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    args = ap.parse_args()

    data = json.load(open(DATA, encoding="utf-8"))
    group_slugs = [g["slug"] for g in data["groups"]]
    known = {p["file"] for p in data["photos"]}
    errors, plan = [], []

    for src in args.photos:
        src = os.path.expanduser(src)
        if not os.path.isfile(src):
            errors.append(f"not found: {src}")
            continue
        slug = slug_from_filename(src)
        fn = os.path.basename(src)
        if os.path.splitext(fn)[1].lower() not in (".jpg", ".jpeg"):
            errors.append(f"{fn}: only JPEG files are supported")
            continue
        rel = f"{slug}/{fn}"
        if rel in known or os.path.exists(os.path.join(GALLERY, rel)):
            errors.append(f"{fn}: already on the site as {rel} (rename it, e.g. next number)")
            continue
        new_species = slug not in data["species"]
        if new_species and not args.group:
            errors.append(f'{fn}: "{slug}" is a new species; add --group (one of: {", ".join(group_slugs)})'
                          f' and, if needed, --name "Display Name"')
            continue
        if new_species and args.group not in group_slugs:
            errors.append(f'--group "{args.group}" is not one of: {", ".join(group_slugs)}')
            continue
        name = data["species"][slug]["name"] if not new_species else (
            args.name or " ".join(w.capitalize() for w in slug.split("-")))
        parts = [name] + ([args.location] if args.location else []) + [m for m in [capture_month(src)] if m]
        w, h = pixel_size(src)
        plan.append({"src": src, "slug": slug, "rel": rel, "name": name, "new": new_species,
                     "caption": ", ".join(parts), "portrait": h > w})
        known.add(rel)

    if errors:
        sys.exit("Nothing was changed:\n  " + "\n  ".join(errors))

    for p in plan:
        tag = " (new species, group: %s)" % args.group if p["new"] else ""
        print(f'{os.path.basename(p["src"])} -> assets/img/gallery/{p["rel"]}{tag}\n'
              f'    caption: {p["caption"]}' + ("\n    home page: yes" if args.home else ""))
    if args.dry_run:
        print("Dry run: nothing changed.")
        return

    for p in plan:
        dest_dir = os.path.join(GALLERY, p["slug"])
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(p["rel"]))
        w, h = pixel_size(p["src"])
        if max(w, h) > LONG_EDGE:
            subprocess.run(["sips", "-Z", str(LONG_EDGE), "-s", "formatOptions", str(JPEG_QUALITY),
                            p["src"], "--out", dest], capture_output=True, check=True)
        else:
            shutil.copy2(p["src"], dest)

        if p["new"]:
            data["species"][p["slug"]] = {"name": p["name"], "group": args.group}
        entry = {"file": p["rel"], "caption": p["caption"]}
        # keep each species' photos together: insert after the last photo of the same species
        idx = max((i for i, e in enumerate(data["photos"]) if e["file"].startswith(p["slug"] + "/")),
                  default=len(data["photos"]) - 1)
        data["photos"].insert(idx + 1, entry)

    if args.home:
        # newest first, in the order given on the command line
        data["home"] = [p["rel"] for p in plan] + data["home"]

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    sys.stdout.flush()  # print the summary above before the build output
    subprocess.run([sys.executable, os.path.join(SITE, "scripts/build_site.py")], check=True)


if __name__ == "__main__":
    main()
