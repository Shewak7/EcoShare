import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import joblib

# Step 1: Start the script
print("Script started...")

# Step 2: Load NGO Data
try:
    print("Loading NGO data...")
    ngo_df = pd.read_csv("ngo_data_chennai.csv")
    print("NGO data loaded successfully!")
    print(ngo_df.head())  # Print first few rows to verify data
except Exception as e:
    print(f"Error loading NGO data: {e}")
    exit()

# Step 3: Define Features (Including Age)
feature_columns = ["Average Age of Beneficiaries", "People Count", "Last Food Received (hrs)", "Food Stock Level (%)"]
if not all(col in ngo_df.columns for col in feature_columns):
    print("Error: One or more required feature columns are missing!")
    exit()

X = ngo_df[feature_columns]

# Step 4: Compute Urgency Score with Higher Food Stock Weight
print("Generating urgency scores...")
y = ((100 - ngo_df["Food Stock Level (%)"]) * 1.5 +  # Increased weight for food stock
     ngo_df["Last Food Received (hrs)"] * 1.0 +  # Normal weight for last received
     (ngo_df["People Count"] / 2) + 
     (ngo_df["Average Age of Beneficiaries"] / 2))

# Step 5: Split Data for Training
print("Splitting data into training and testing sets...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Step 6: Train Random Forest Model
print(f"Training RandomForestRegressor on {X_train.shape[0]} samples...")
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Step 7: Save the Model
joblib.dump(model, "urgency_model_1.pkl")
print("Model trained and saved as 'urgency_model_1.pkl'")

# Step 8: Predict Urgency Scores for All NGOs
print("Predicting urgency scores for all NGOs...")
ngo_df["Urgency Score"] = model.predict(X)

# Debugging Step: Print first few urgency scores
print(ngo_df[["NGO Name", "Urgency Score"]].head())

# Step 9: Save Updated NGO Data
ngo_df.to_csv("ngo_data_with_urgency.csv", index=False)
print("CSV file 'ngo_data_with_urgency.csv' saved successfully!")

print("Script execution completed successfully!")
