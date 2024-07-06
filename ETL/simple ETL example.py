import os
import sys
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, DateType, DecimalType, IntegerType

os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable



# Build SparkSession
spark = SparkSession.builder.master("local[1]").appName("ETL Pipeline").getOrCreate()

# Set Logging Level to WARN
spark.sparkContext.setLogLevel("WARN")

###############################################################
#######################   EXTRACT  ############################
###############################################################


source_data_file = "./data/files/prices.csv"

# Define csv input schema
schema = StructType([
    StructField("symbol", StringType()),
    StructField("date", DateType()),
    StructField("open", DecimalType(precision=38, scale=2)),
    StructField("high", DecimalType(precision=38, scale=2)),
    StructField("low", DecimalType(precision=38, scale=2)),
    StructField("close", DecimalType(precision=38, scale=2)),
    StructField("volume", IntegerType()),
    StructField("adj_close", DecimalType(precision=38, scale=2))
])


data = spark.read.option("header",True).csv(source_data_file, schema=schema).cache()
data.printSchema()


count = data.count()

data.show()

print("Data points from files count: {}".format(count))

###############################################################
#######################   TRANSFORM  ##########################
###############################################################


import pandas as pd
df = pd.DataFrame(data)

df_count = df.count()

### Filter any NULL symbols
df2 = df.filter("date is not NULL")

df2_count = df2.count()
print("Data points remaining after removing nulls: {}".format(df2_count))

print("Removed {} nulls".format(df_count - df2_count))



from pyspark.sql.functions import expr
df2 = df2.withColumn("new_column", expr("high-low"))
#df2 = df2.withColumnRenamed("new_column", "high-low")

df2.show()



###############################################################
#########################   LOAD  #############################
###############################################################

print("Starting DB write")

df2.write.save('/target/path/', format='parquet', mode='append')
