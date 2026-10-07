import sys, pandas as pd
df = pd.read_csv(sys.argv[1])
print(df.shape); print(df.head(10).to_string())
print("\nTYPES:\n", df["type_of_emissions"].value_counts().to_string())
print("\nUNITS:\n", df["unit"].value_counts().to_string())
print("\nSECTORS:", df["sector"].nunique(), " COMPANIES:", df["company_name"].nunique())
