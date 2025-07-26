import psycopg2
import select
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import joblib

# Load trained Random Forest Model
model = joblib.load("urgency_model_1.pkl")

# Connect to PostgreSQL
conn = psycopg2.connect(
    dbname="food",
    user="postgres",
    password="postgres",
    host="localhost",
    port="5432"
)
conn.autocommit = True
cursor = conn.cursor()

# Listen for donor_insert event
cursor.execute("LISTEN donor_insert;")
print("Listening for new donor entries...")

while True:
    conn.poll()
    while conn.notifies:
        notify = conn.notifies.pop(0)
        donor_id = notify.payload  # Get the donor ID from the notification
        print(f"New donor added: {donor_id}. Running matching algorithm...")

        # Fetch all NGOs from the database
        cursor.execute("""
            SELECT ngo_id, ngo_name, latitude, longitude, people_count, last_food_received, 
                   food_stock_level, urgency_score, average_age 
            FROM ngos;
        """)
        ngo_records = cursor.fetchall()

        # Convert NGO data into a DataFrame
        ngo_columns = ["NGO ID", "NGO Name", "Latitude", "Longitude", 
                       "People Count", "Last Food Received (hrs)", "Food Stock Level (%)", 
                       "Urgency Score", "Average Age of Beneficiaries"]
        ngo_df = pd.DataFrame(ngo_records, columns=ngo_columns)

        # Fetch the newly added donor (matching donor_id)
        cursor.execute("""
            SELECT donor_id, donor_name, latitude, longitude, food_quantity, timestamp 
            FROM donors 
            WHERE donor_id = %s;
        """, (donor_id,))
        donor_records = cursor.fetchall()

        # Convert donor data into DataFrame
        donor_columns = ["Donor ID", "Donor Name", "Latitude", "Longitude", "Food Quantity", "Timestamp"]
        donor_df = pd.DataFrame(donor_records, columns=donor_columns)

        if donor_df.empty:
            print(f"No donor found with ID {donor_id}.")
            continue

        # Convert locations to numpy arrays
        ngo_locations = ngo_df[["Latitude", "Longitude"]].to_numpy()
        donor_locations = donor_df[["Latitude", "Longitude"]].to_numpy()

        # Build KDTree for NGO locations
        ngo_tree = cKDTree(ngo_locations)

        # Store matches
        matches = []
        matched_ngos = set()
        for i, donor in donor_df.iterrows():
            donor_location = donor_locations[i]

            # Find NGOs within 10 km (1 degree ≈ 111 km)
            indices = ngo_tree.query_ball_point(donor_location, 10 / 111)

            if indices:
                nearby_ngos = ngo_df.iloc[indices].copy()
                nearby_ngos["Distance (km)"] = np.linalg.norm(ngo_locations[indices] - donor_location, axis=1) * 111

                # Predict urgency score dynamically (including Average Age)
                urgency_features = nearby_ngos[["Average Age of Beneficiaries", "People Count", 
                                                "Last Food Received (hrs)", "Food Stock Level (%)"]]
                nearby_ngos["Urgency Score"] = model.predict(urgency_features)

                # Sort by urgency
                nearby_ngos = nearby_ngos.sort_values(by="Urgency Score", ascending=False)

                # Assign the best match
                best_match = nearby_ngos.iloc[0]
                matched_ngos.add(best_match["NGO ID"])

                matches.append((
                    int(donor["Donor ID"]),  # Convert numpy int64 to standard int
                    int(best_match["NGO ID"]),  
                    float(donor["Food Quantity"]),  # Convert numpy float to standard float
                    float(best_match["Distance (km)"]),  
                    float(best_match["Urgency Score"]),  
                ))

        # Insert matches into the database
        insert_query = """
        INSERT INTO donor_ngo_matches (donor_id, ngo_id, food_quantity, distance_km, urgency_before)
        VALUES (%s, %s, %s, %s, %s);
        """
        cursor.executemany(insert_query, matches)

        # Update details for matched NGOs
        for match in matches:
            ngo_id = match[1]
            received_food = match[2]

            # Fetch current stock level for the NGO
            cursor.execute("""
                SELECT food_stock_level FROM ngos WHERE ngo_id = %s;
            """, (ngo_id,))
            current_stock = cursor.fetchone()[0]  # Get current stock level

            # Calculate new stock level (ensure it doesn't exceed 100%)
            new_stock_level = min(float(current_stock) + float((received_food) / 2), 100)

            # Update NGO details: reset last received time, update stock level
            update_query = """
            UPDATE ngos 
            SET  
                last_food_received = 0, 
                food_stock_level = %s 
            WHERE ngo_id = %s;
            """
            cursor.execute(update_query, (new_stock_level, ngo_id))

        # Update urgency scores for all NGOs (including unmatched ones)
        for _, row in ngo_df.iterrows():
            ngo_id = row["NGO ID"]
            if ngo_id not in matched_ngos:  # Skip already updated ones
                urgency_features = pd.DataFrame([[row["Average Age of Beneficiaries"], row["People Count"], 
                                  row["Last Food Received (hrs)"] + 1, row["Food Stock Level (%)"]]], 
                                  columns=["Average Age of Beneficiaries", "People Count", 
                                           "Last Food Received (hrs)", "Food Stock Level (%)"])

                new_urgency = float(model.predict(urgency_features)[0])  # ✅ Now matches trained model

                # Update the urgency score for unmatched NGOs (increase last received time)
                cursor.execute("""
                    UPDATE ngos 
                    SET urgency_score = %s, last_food_received = last_food_received + 1
                    WHERE ngo_id = %s;
                """, (new_urgency, ngo_id))

        # Commit changes
        conn.commit()
        print(f"NGO details updated with new stock levels, urgency scores, and last received times.")
