# Databricks notebook source
# MAGIC %md
# MAGIC # Silver 02 — chunks
# MAGIC Split each document's `full_text` into character windows (see `go_opps.chunking`).
# MAGIC
# MAGIC Small documents produce a single chunk (the common case today); long ones split
# MAGIC into overlapping windows so no window exceeds the model's comfortable input size.
# MAGIC Extraction (03) runs per chunk. `char_start`/`char_end` index into `full_text`, so a
# MAGIC citation quote can be located later.

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_fde_hackathon_catalog")
dbutils.widgets.text("schema", "brickhearts")
dbutils.widgets.text("max_chars", "6000")
dbutils.widgets.text("overlap", "400")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
max_chars = int(dbutils.widgets.get("max_chars"))
overlap = int(dbutils.widgets.get("overlap"))
print(f"Chunking {catalog}.{schema}.silver_documents (max_chars={max_chars}, overlap={overlap})")

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, IntegerType, StringType, StructField, StructType

from go_opps.chunking import chunk_text

_chunk_struct = ArrayType(
    StructType(
        [
            StructField("chunk_index", IntegerType()),
            StructField("char_start", IntegerType()),
            StructField("char_end", IntegerType()),
            StructField("text", StringType()),
        ]
    )
)


@F.udf(returnType=_chunk_struct)
def chunk_udf(text):
    return [(c.chunk_index, c.char_start, c.char_end, c.text) for c in chunk_text(text, max_chars, overlap)]


docs = spark.table(f"{catalog}.{schema}.silver_documents").select("document_id", "full_text")
chunks = (
    docs.withColumn("chunk", F.explode(chunk_udf("full_text")))
    .select(
        F.sha2(F.concat_ws("#", "document_id", F.col("chunk.chunk_index").cast("string")), 256).alias("chunk_id"),
        "document_id",
        F.col("chunk.chunk_index").alias("chunk_index"),
        F.col("chunk.char_start").alias("char_start"),
        F.col("chunk.char_end").alias("char_end"),
        F.col("chunk.text").alias("text"),
    )
)
chunks.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.{schema}.silver_chunks")

# COMMAND ----------

n_docs = docs.count()
n_chunks = spark.table(f"{catalog}.{schema}.silver_chunks").count()
print(f"{n_chunks} chunks from {n_docs} documents (avg {n_chunks / max(n_docs, 1):.2f} chunks/doc)")
display(
    spark.sql(
        f"SELECT document_id, count(*) AS n_chunks FROM {catalog}.{schema}.silver_chunks "
        f"GROUP BY document_id HAVING count(*) > 1 ORDER BY n_chunks DESC LIMIT 10"
    )
)
