# Databricks notebook source
# MAGIC %md
# MAGIC # Reference — Census FIPS gazetteer (NY / CA / VA)
# MAGIC Builds the place reference used to canonicalize extracted geography to real FIPS ids:
# MAGIC
# MAGIC - `silver_ref_gazetteer` — one row per real place: `geoid` (FIPS), name, level
# MAGIC   (`nation`/`state`/`county`/`place`), `usps`, `parent_geoid` (→ state).
# MAGIC - `silver_ref_place_alias` — `(alias_norm, usps) → geoid`, so an extracted name joins
# MAGIC   to a canonical place. On a shared name, **county beats city** (state beats both), which
# MAGIC   collapses "San Diego" / "San Diego County" / "City of San Diego" onto one place_id.
# MAGIC
# MAGIC Reference data — runs rarely, not part of the per-signal pipeline. Downloads the US
# MAGIC Census Gazetteer files; if egress is blocked, stage the two files into a UC Volume and
# MAGIC set `gaz_base` to that path.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
dbutils.widgets.text("year", "2023")
dbutils.widgets.text("gaz_base", "https://www2.census.gov/geo/docs/maps-data/data/gazetteer")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
year = dbutils.widgets.get("year")
gaz_base = dbutils.widgets.get("gaz_base").rstrip("/")

import io
import re
import urllib.request
import zipfile

import pandas as pd

from go_opps.resolution import normalize_place_name

# NY / CA / VA
STATES = {"CA": ("06", "California"), "NY": ("36", "New York"), "VA": ("51", "Virginia")}
_LSAD_SUFFIX = re.compile(r"\s+(city and borough|municipality|city|town|village|borough|CDP|county)$", re.I)

# COMMAND ----------


def _load_gaz(kind: str) -> pd.DataFrame:
    """Download a national gazetteer zip and return the parsed, state-filtered frame."""
    url = f"{gaz_base}/{year}_Gazetteer/{year}_Gaz_{kind}_national.zip"
    print("fetching", url)
    raw = urllib.request.urlopen(url, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = z.namelist()[0]
        df = pd.read_csv(z.open(name), sep="\t", dtype=str, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    df = df[df["USPS"].isin(STATES)].copy()
    df["GEOID"] = df["GEOID"].str.strip()
    df["NAME"] = df["NAME"].str.strip()
    return df


counties = _load_gaz("counties")
places = _load_gaz("place")
print(f"counties={len(counties)} places={len(places)}")

# COMMAND ----------

rows = []  # (geoid, name, level, usps, parent_geoid)
rows.append(("us", "United States", "nation", "US", None))
for usps, (fips, name) in STATES.items():
    rows.append((fips, name, "state", usps, "us"))
for _, r in counties.iterrows():
    rows.append((r["GEOID"], r["NAME"], "county", r["USPS"], STATES[r["USPS"]][0]))
for _, r in places.iterrows():
    clean = _LSAD_SUFFIX.sub("", r["NAME"]).strip()
    rows.append((r["GEOID"], clean, "place", r["USPS"], STATES[r["USPS"]][0]))

gaz = pd.DataFrame(rows, columns=["geoid", "canonical_name", "level", "usps", "parent_geoid"])
spark.createDataFrame(gaz).write.mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"{catalog}.{schema}.silver_ref_gazetteer")
print("silver_ref_gazetteer:", len(gaz))

# COMMAND ----------

# Alias variants per entry → normalized key. county beats place on a shared name.
_PRIORITY = {"nation": 0, "state": 1, "county": 2, "place": 3}
alias_rows = []


def _variants(name: str, level: str) -> list[str]:
    v = [name]
    if level == "county":
        v.append(re.sub(r"\s+county$", "", name, flags=re.I))       # "San Diego County" -> "San Diego"
    if level == "place":
        v += [f"City of {name}", f"Town of {name}"]
    if level == "nation":
        v += ["US", "USA", "U.S.", "United States of America"]
    return v


for _, g in gaz.iterrows():
    for variant in _variants(g["canonical_name"], g["level"]):
        an = normalize_place_name(variant)
        if an:
            alias_rows.append((an, g["usps"], g["geoid"], g["canonical_name"], g["level"], _PRIORITY[g["level"]]))

alias = pd.DataFrame(alias_rows, columns=["alias_norm", "usps", "geoid", "canonical_name", "level", "prio"])
# on a shared (alias_norm, usps), keep the highest-priority entry (state>county>place)
alias = alias.sort_values("prio").drop_duplicates(["alias_norm", "usps"], keep="first")
alias = alias.drop(columns=["prio"])

spark.createDataFrame(alias).write.mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"{catalog}.{schema}.silver_ref_place_alias")
print("silver_ref_place_alias:", len(alias))

# COMMAND ----------

display(spark.sql(f"""
SELECT alias_norm, usps, geoid, canonical_name, level
FROM {catalog}.{schema}.silver_ref_place_alias
WHERE alias_norm IN ('san diego','los angeles','new york','richmond','fairfax')
ORDER BY alias_norm, usps
"""))
