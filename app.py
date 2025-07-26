from flask import Flask, render_template, request, jsonify
import psycopg2
from datetime import datetime

app = Flask(__name__)

# PostgreSQL DB configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'food',
    'user': 'postgres',
    'password': 'postgres',
    'port': '5432'
}

def get_connection():
    """Connect to PostgreSQL database."""
    return psycopg2.connect(**DB_CONFIG)

@app.route('/')
def home():
    return render_template('home.html')  # HTML file should be in templates/

@app.route('/donor_form')
def donor_form():
    return render_template('donor_form.html')

@app.route('/submit_donor', methods=['POST'])
def submit_donor():
    try:
        donor_name = request.form['donor_name']
        food_quantity = float(request.form['food_quantity'])
        latitude = float(request.form['latitude'])
        longitude = float(request.form['longitude'])
        timestamp = datetime.now()

        conn = get_connection()
        cur = conn.cursor()

        insert_query = '''
        INSERT INTO donors (donor_name, food_quantity, latitude, longitude, timestamp)
        VALUES (%s, %s, %s, %s, %s) RETURNING donor_id;
        '''
        cur.execute(insert_query, (donor_name, food_quantity, latitude, longitude, timestamp))
        donor_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'donor_id': donor_id}), 200

    except Exception as e:
        print("Error inserting donor:", e)
        return jsonify({'error': 'Failed to insert donor'}), 500

@app.route('/get_matched_ngo_name/<int:donor_id>', methods=['GET'])
def get_matched_ngo_name(donor_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Get matched NGO ID from donor_ngo_matches
        cur.execute("SELECT ngo_id FROM donor_ngo_matches WHERE donor_id = %s", (donor_id,))
        result = cur.fetchone()

        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'No match found for given donor ID'}), 404

        ngo_id = result[0]

        # Get NGO name from ngos table
        cur.execute("SELECT ngo_name FROM ngos WHERE ngo_id = %s", (ngo_id,))
        ngo_result = cur.fetchone()

        cur.close()
        conn.close()

        if ngo_result:
            return jsonify({'ngo_name': ngo_result[0]}), 200
        else:
            return jsonify({'error': 'NGO not found for given ID'}), 404

    except Exception as e:
        print("Error:", e)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/view_directions/<int:donor_id>')
def view_directions(donor_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Get donor coordinates
        cur.execute("SELECT latitude, longitude FROM donors WHERE donor_id = %s", (donor_id,))
        donor_coords = cur.fetchone()

        # Get matched NGO ID
        cur.execute("SELECT ngo_id FROM donor_ngo_matches WHERE donor_id = %s", (donor_id,))
        ngo_result = cur.fetchone()
        if not ngo_result:
            return "No matched NGO found", 404

        ngo_id = ngo_result[0]

        # Get NGO coordinates
        cur.execute("SELECT latitude, longitude FROM ngos WHERE ngo_id = %s", (ngo_id,))
        ngo_coords = cur.fetchone()

        cur.close()
        conn.close()

        if donor_coords and ngo_coords:
            return render_template("map_directions.html",
                                   donor_lat=donor_coords[0], donor_lng=donor_coords[1],
                                   ngo_lat=ngo_coords[0], ngo_lng=ngo_coords[1])
        else:
            return "Coordinates not found", 404

    except Exception as e:
        print("Error:", e)
        return "Internal server error", 500

if __name__ == '__main__':
    app.run(debug=True)
