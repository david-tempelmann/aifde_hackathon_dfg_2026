# Databricks notebook source
# MAGIC %md
# MAGIC # Reference — Census FIPS gazetteer (all 50 states + DC)
# MAGIC Builds the place reference used to canonicalize extracted geography to real FIPS ids:
# MAGIC
# MAGIC - `silver_ref_gazetteer` — one row per real place: `geoid` (FIPS), name, level
# MAGIC   (`nation`/`state`/`county`/`place`), `usps`, `parent_geoid` (→ state), `lat`/`lon`
# MAGIC   (internal point; state/nation points derived as the mean of their children).
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

# All 50 states + DC → (state FIPS, name). The gazetteer covers the whole US so
# extracted geography resolves nationwide; the frontend filters to the states GO
# cares about. Territories (PR/GU/VI/…) are intentionally excluded — this dict is
# also the row filter applied in _load_gaz.
STATES = {
    "AL": ("01", "Alabama"), "AK": ("02", "Alaska"), "AZ": ("04", "Arizona"),
    "AR": ("05", "Arkansas"), "CA": ("06", "California"), "CO": ("08", "Colorado"),
    "CT": ("09", "Connecticut"), "DE": ("10", "Delaware"),
    "DC": ("11", "District of Columbia"), "FL": ("12", "Florida"),
    "GA": ("13", "Georgia"), "HI": ("15", "Hawaii"), "ID": ("16", "Idaho"),
    "IL": ("17", "Illinois"), "IN": ("18", "Indiana"), "IA": ("19", "Iowa"),
    "KS": ("20", "Kansas"), "KY": ("21", "Kentucky"), "LA": ("22", "Louisiana"),
    "ME": ("23", "Maine"), "MD": ("24", "Maryland"), "MA": ("25", "Massachusetts"),
    "MI": ("26", "Michigan"), "MN": ("27", "Minnesota"), "MS": ("28", "Mississippi"),
    "MO": ("29", "Missouri"), "MT": ("30", "Montana"), "NE": ("31", "Nebraska"),
    "NV": ("32", "Nevada"), "NH": ("33", "New Hampshire"), "NJ": ("34", "New Jersey"),
    "NM": ("35", "New Mexico"), "NY": ("36", "New York"), "NC": ("37", "North Carolina"),
    "ND": ("38", "North Dakota"), "OH": ("39", "Ohio"), "OK": ("40", "Oklahoma"),
    "OR": ("41", "Oregon"), "PA": ("42", "Pennsylvania"), "RI": ("44", "Rhode Island"),
    "SC": ("45", "South Carolina"), "SD": ("46", "South Dakota"), "TN": ("47", "Tennessee"),
    "TX": ("48", "Texas"), "UT": ("49", "Utah"), "VT": ("50", "Vermont"),
    "VA": ("51", "Virginia"), "WA": ("53", "Washington"), "WV": ("54", "West Virginia"),
    "WI": ("55", "Wisconsin"), "WY": ("56", "Wyoming"),
}
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

# INTPTLAT/INTPTLONG arrive as strings (and can carry a leading '+'); coerce to
# double up front so both the seed centroids and the per-row coords are numeric.
for _df in (counties, places):
    _df["INTPTLAT"] = pd.to_numeric(_df["INTPTLAT"], errors="coerce")
    _df["INTPTLONG"] = pd.to_numeric(_df["INTPTLONG"], errors="coerce")

# The county/place files carry no nation or state row, so derive a representative
# map point for each: state = mean of its counties' internal points, nation =
# mean of the state points. Keeps the seed rows maintenance-free (no hand-kept
# centroid table) and correct as the state set grows.
_state_pt = counties.groupby("USPS")[["INTPTLAT", "INTPTLONG"]].mean()
_us_lat, _us_lon = _state_pt["INTPTLAT"].mean(), _state_pt["INTPTLONG"].mean()

# COMMAND ----------

rows = []  # (geoid, name, level, usps, parent_geoid, lat, lon)
rows.append(("us", "United States", "nation", "US", None, _us_lat, _us_lon))
for usps, (fips, name) in STATES.items():
    slat = _state_pt.at[usps, "INTPTLAT"] if usps in _state_pt.index else None
    slon = _state_pt.at[usps, "INTPTLONG"] if usps in _state_pt.index else None
    rows.append((fips, name, "state", usps, "us", slat, slon))
for _, r in counties.iterrows():
    rows.append((r["GEOID"], r["NAME"], "county", r["USPS"], STATES[r["USPS"]][0],
                 r["INTPTLAT"], r["INTPTLONG"]))
for _, r in places.iterrows():
    clean = _LSAD_SUFFIX.sub("", r["NAME"]).strip()
    rows.append((r["GEOID"], clean, "place", r["USPS"], STATES[r["USPS"]][0],
                 r["INTPTLAT"], r["INTPTLONG"]))

gaz = pd.DataFrame(rows, columns=["geoid", "canonical_name", "level", "usps", "parent_geoid", "lat", "lon"])
gaz["lat"] = pd.to_numeric(gaz["lat"], errors="coerce")
gaz["lon"] = pd.to_numeric(gaz["lon"], errors="coerce")
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
