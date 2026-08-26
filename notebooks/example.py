# Databricks notebook source
dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
print(f"Using {catalog}.{schema}")

# COMMAND ----------

import go_opps

print(go_opps.__version__)
