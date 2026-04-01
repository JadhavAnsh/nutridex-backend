import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

# Load the dataset
file_path = "models/processed_nutritional_dataset.csv"
df = pd.read_csv(file_path)

# Drop unwanted columns
df.drop(columns=["Processed Level", "Product Name", "Category"], inplace=True)

# Normalize nutrition facts based on serving size
df["Serving Size (g)"] = df["Serving Size"].str.extract(r'(\d+)').astype(float)
columns_to_normalize = ["Calories", "Protein (g)", "Fats (g)", "Carbohydrates (g)", "Sugars (g)", "Sodium (mg)",
                         "Saturated Fat (g)", "Trans Fat (g)", "Cholesterol (mg)"]

for col in columns_to_normalize:
    df[col] = (df[col] / df["Serving Size (g)"]) * 100

# Drop the original Serving Size column
df.drop(columns=["Serving Size", "Serving Size (g)"], inplace=True)

# Encode categorical target variable "Health Classification"
label_encoder = LabelEncoder()
df["Health Classification"] = label_encoder.fit_transform(df["Health Classification"].astype(str))

# Define features (X) and targets (y)
X = df.drop(columns=["Health Classification", "Nutrition Score"])
y = df[["Health Classification", "Nutrition Score"]]

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Train a Multi-Output Regression Model
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Save the trained model
joblib.dump(model, "models/chirag_patil.pkl")

# Evaluate the model
y_pred = model.predict(X_test)
mae = mean_absolute_error(y_test, y_pred)
print(f"Mean Absolute Error: {mae}")
