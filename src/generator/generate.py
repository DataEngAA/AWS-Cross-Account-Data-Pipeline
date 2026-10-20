"""Generate synthetic product-price files for the producer account (Account A).

Files are written in the same layout as the raw S3 bucket, so the upload step
can mirror the local folder:

    <out>/raw/source=synthetic/date=YYYY-MM-DD/<run_id>.json

A fixed product catalogue is reused across files, so the same product appears
on several days with a slightly different price. A share of records is broken
on purpose (see BAD_KINDS) so Glue Data Quality has something to catch.
`<out>/manifest.json` records exactly how many bad records of each kind every
file contains, so quarantine counts can be checked later.

Standard library only. Same --seed and --start always give the same output.
"""

import argparse
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE = "synthetic"

CATEGORIES = {
    "Books": (4, 40),
    "Electronics": (15, 900),
    "Toys": (5, 120),
    "Grocery": (1, 25),
    "Home": (8, 300),
    "Clothing": (6, 150),
    "Sports": (10, 400),
    "Beauty": (3, 80),
}
CURRENCIES = ["GBP", "USD", "EUR"]
ADJECTIVES = ["Classic", "Smart", "Organic", "Compact", "Deluxe", "Eco", "Pro",
              "Mini", "Ultra", "Vintage", "Wireless", "Premium", "Everyday"]
NOUNS = {
    "Books": ["Novel", "Cookbook", "Atlas", "Guide", "Anthology", "Workbook"],
    "Electronics": ["Headphones", "Speaker", "Charger", "Monitor", "Keyboard", "Camera"],
    "Toys": ["Puzzle", "Robot", "Board Game", "Building Set", "Plush Bear", "Kite"],
    "Grocery": ["Coffee", "Olive Oil", "Granola", "Green Tea", "Honey", "Pasta"],
    "Home": ["Lamp", "Kettle", "Blanket", "Vase", "Frying Pan", "Towel Set"],
    "Clothing": ["Jacket", "T-Shirt", "Scarf", "Sneakers", "Hoodie", "Jeans"],
    "Sports": ["Yoga Mat", "Football", "Dumbbell", "Tennis Racket", "Water Bottle", "Helmet"],
    "Beauty": ["Face Cream", "Shampoo", "Lip Balm", "Perfume", "Sunscreen", "Soap"],
}

# One entry per deliberate defect. Each maps to a rule in DATA_QUALITY.md.
BAD_KINDS = [
    "missing_price",      # DQ-03
    "negative_price",     # DQ-03
    "invalid_timestamp",  # DQ-05 (not ISO 8601)
    "future_timestamp",   # DQ-05 (in the future)
    "duplicate_id",       # DQ-01
    "empty_name",         # DQ-02
    "invalid_currency",   # DQ-04
    "missing_category",   # DQ-06
]


def build_catalogue(rng, size):
    catalogue = []
    for i in range(1, size + 1):
        category = rng.choice(list(CATEGORIES))
        low, high = CATEGORIES[category]
        catalogue.append({
            "product_id": f"p-{i:05d}",
            "name": f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS[category])}",
            "category": category,
            "base_price": round(rng.uniform(low, high), 2),
            "currency": rng.choice(CURRENCIES),
        })
    return catalogue


def good_record(rng, product, scraped_at):
    # Price drifts up to +/-15% around the base price on every run.
    price = round(product["base_price"] * rng.uniform(0.85, 1.15), 2)
    return {
        "product_id": product["product_id"],
        "name": product["name"],
        "category": product["category"],
        "price": max(price, 0.01),
        "currency": product["currency"],
        "in_stock": rng.random() > 0.1,
        "scraped_at": scraped_at,
        "url": f"https://example.test/{product['product_id']}",
    }


def break_record(rng, record, kind, earlier_ids):
    if kind == "missing_price":
        del record["price"]
    elif kind == "negative_price":
        record["price"] = -round(rng.uniform(0.5, 50), 2)
    elif kind == "invalid_timestamp":
        record["scraped_at"] = rng.choice(["not-a-date", "2026-13-45T25:61:00Z", ""])
    elif kind == "future_timestamp":
        record["scraped_at"] = "2099-01-01T00:00:00Z"
    elif kind == "duplicate_id":
        record["product_id"] = rng.choice(earlier_ids)
    elif kind == "empty_name":
        record["name"] = ""
    elif kind == "invalid_currency":
        record["currency"] = rng.choice(["XXX", "gbp", "US$", ""])
    elif kind == "missing_category":
        record["category"] = None
    return record


def make_file(rng, catalogue, n_records, bad_rate, scraped_at):
    stamp = scraped_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Sample without replacement so duplicates only come from "duplicate_id".
    products = rng.sample(catalogue, min(n_records, len(catalogue)))
    records, bad = [], Counter()
    for product in products:
        record = good_record(rng, product, stamp)
        if records and rng.random() < bad_rate:
            kind = rng.choice(BAD_KINDS)
            earlier_ids = [r["product_id"] for r in records[-50:]]
            record = break_record(rng, record, kind, earlier_ids)
            bad[kind] += 1
        records.append(record)
    return {"source": SOURCE, "scraped_at": stamp, "records": records}, bad


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--files", type=int, default=30, help="number of files (default 30)")
    parser.add_argument("--records", type=int, default=5000, help="records per file (default 5000)")
    parser.add_argument("--products", type=int, default=8000,
                        help="catalogue size; must be >= --records (default 8000)")
    parser.add_argument("--days", type=int, default=7, help="spread files over this many days (default 7)")
    parser.add_argument("--bad-rate", type=float, default=0.05, help="share of bad records (default 0.05)")
    parser.add_argument("--broken-files", type=int, default=1,
                        help="extra files that are not valid JSON (default 1)")
    parser.add_argument("--start", default="2026-10-14",
                        help="first day, YYYY-MM-DD (default 2026-10-14)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data", help="output folder (default data/)")
    args = parser.parse_args()

    if args.records > args.products:
        parser.error("--records cannot be larger than --products")

    rng = random.Random(args.seed)
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(hour=6, tzinfo=timezone.utc)
    out = Path(args.out)
    catalogue = build_catalogue(rng, args.products)

    files_per_day = -(-args.files // args.days)  # ceiling division
    step = timedelta(hours=16 / files_per_day)    # runs between 06:00 and 22:00 UTC
    manifest, total_records, total_bad = [], 0, 0

    for i in range(args.files):
        day, slot = divmod(i, files_per_day)
        scraped_at = start + timedelta(days=day) + slot * step
        run_id = f"{scraped_at:%Y%m%dT%H%M%S}-{i + 1:03d}"
        batch, bad = make_file(rng, catalogue, args.records, args.bad_rate, scraped_at)

        path = out / "raw" / f"source={SOURCE}" / f"date={scraped_at:%Y-%m-%d}" / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(batch), encoding="utf-8")

        n_bad = sum(bad.values())
        total_records += len(batch["records"])
        total_bad += n_bad
        manifest.append({"key": path.relative_to(out).as_posix(), "run_id": run_id,
                         "records": len(batch["records"]), "bad": n_bad, "bad_by_kind": dict(bad)})

    for j in range(args.broken_files):
        scraped_at = start + timedelta(days=j % args.days, hours=23)
        run_id = f"{scraped_at:%Y%m%dT%H%M%S}-broken-{j + 1:02d}"
        path = out / "raw" / f"source={SOURCE}" / f"date={scraped_at:%Y-%m-%d}" / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"source": "synthetic", "records": [{"product_id": "p-0', encoding="utf-8")
        manifest.append({"key": path.relative_to(out).as_posix(), "run_id": run_id,
                         "records": None, "bad": None, "broken": True})

    (out / "manifest.json").write_text(json.dumps({
        "seed": args.seed, "files": args.files, "broken_files": args.broken_files,
        "total_records": total_records, "total_bad": total_bad, "files_detail": manifest,
    }, indent=2), encoding="utf-8")

    print(f"wrote {args.files} files + {args.broken_files} broken file(s) to {out}/raw/")
    print(f"records: {total_records:,}  bad: {total_bad:,} ({total_bad / max(total_records, 1):.1%})")
    print(f"details per file: {out}/manifest.json")


if __name__ == "__main__":
    main()
