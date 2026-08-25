from functools import wraps
import os
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_connection
from psycopg2.extras import RealDictCursor
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
def login_required():

    if "user_id" not in session:
        return False

    return True


def admin_api_required(view):
    """Limit admin data APIs to authenticated admin accounts."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "Administrator access required"}), 403
        return view(*args, **kwargs)
    return wrapped


def driver_api_required(view):
    """Limit driver APIs to the signed-in driver account."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        if session.get("role") != "driver":
            return jsonify({"error": "Driver access required"}), 403
        return view(*args, **kwargs)
    return wrapped


def password_matches(stored_password, submitted_password):
    """Support existing plain-text accounts while newly created accounts use hashes."""
    if stored_password.startswith(("scrypt:", "pbkdf2:")):
        return check_password_hash(stored_password, submitted_password)
    return stored_password == submitted_password


def date_filter(column):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not start_date or not end_date:
        return "", []

    return (
        f" AND {column} >= %s "
        f"AND {column} < (%s::date + INTERVAL '1 day')",
        [start_date, end_date]
    )

# ==========================================
# LOGIN
# ==========================================

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            return """
            <script>
                alert("Please enter email and password");
                window.location.href = "/";
            </script>
            """

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id, name, email, password, role
            FROM users
            WHERE email = %s
        """, (email,))

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and password_matches(user[3], password):

            session["user_id"] = user[0]
            session["name"] = user[1]
            session["email"] = user[2]
            session["role"] = user[4]

            if user[4] == "admin":
                return redirect(url_for("admin_dashboard"))

            elif user[4] == "driver":
                return redirect(url_for("driver_dashboard"))

        return """
        <script>
            alert("Invalid email or password");
            window.location.href = "/";
        </script>
        """

    return render_template("login.html")
# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        role = request.form["role"]

        # Check password confirmation
        if password != confirm_password:

            return """
            <script>
                alert("Passwords do not match");
                window.location.href = "/register";
            </script>
            """

        connection = get_connection()

        cursor = connection.cursor()

        # Check if email already exists
        cursor.execute("""
            SELECT id
            FROM users
            WHERE email = %s
        """, (email,))

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()
            connection.close()

            return """
            <script>
                alert("Email already registered");
                window.location.href = "/register";
            </script>
            """

        # Insert user
        cursor.execute("""
            INSERT INTO users
            (name, email, password, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, generate_password_hash(password), role))

        connection.commit()

        cursor.close()
        connection.close()

        return """
        <script>
            alert("Account created successfully!");
            window.location.href = "/";
        </script>
        """

    return render_template("register.html")


@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return redirect(url_for("driver_dashboard"))

    return render_template("admin/dashboard.html")

@app.route("/driver/prediction")
def driver_prediction():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "driver":
        return redirect(url_for("admin_dashboard"))

    return render_template("driver/prediction.html")

@app.route("/driver")
def driver_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "driver":
        return redirect(url_for("admin_dashboard"))

    return render_template("driver/dashboard.html")


@app.route("/admin/vehicles")
def admin_vehicles():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return redirect(url_for("driver_dashboard"))

    return render_template("admin/vehicles.html")


@app.route("/admin/maintenance")
def admin_maintenance():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return redirect(url_for("driver_dashboard"))

    return render_template("admin/maintenance.html")


@app.route("/admin/revenue")
def admin_revenue():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return redirect(url_for("driver_dashboard"))

    return render_template("admin/revenue.html")


@app.route("/admin/electricity")
def admin_electricity():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return redirect(url_for("driver_dashboard"))

    return render_template("admin/electricity.html")


@app.route("/admin/driver-behaviour")
def admin_driver_behaviour():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "admin":
        return redirect(url_for("driver_dashboard"))

    return render_template("admin/driver_behaviour.html")



# ==========================================
# DRIVER DATA APIs
# ==========================================

@app.route("/api/driver/dashboard")
@driver_api_required
def driver_dashboard_api():
    """Return the newest reading for the signed-in driver's assigned vehicle."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            v.vehicle_number, v.make, v.model, v.status,
            vr.battery_percentage, vr.battery_temperature,
            vr.motor_temperature, vr.speed, vr.city,
            vr.charging_status, vr.recorded_at
        FROM vehicles v
        LEFT JOIN vehicle_readings vr ON vr.id = (
            SELECT MAX(vr2.id)
            FROM vehicle_readings vr2
            WHERE vr2.vehicle_id = v.id
        )
        WHERE v.assigned_driver_id = %s
        ORDER BY v.id
        LIMIT 1
    """, (session["user_id"],))
    vehicle = cursor.fetchone()
    cursor.close()
    connection.close()
    return jsonify(vehicle or {})


@app.route("/api/driver/vehicles")
@driver_api_required
def driver_vehicles_api():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT vehicle_number, make, model
        FROM vehicles
        WHERE assigned_driver_id = %s
        ORDER BY vehicle_number
    """, (session["user_id"],))
    vehicles = cursor.fetchall()
    cursor.close()
    connection.close()
    return jsonify(vehicles)


@app.route("/api/driver/predictions", methods=["GET", "POST"])
@driver_api_required
def driver_predictions_api():
    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "GET":
        cursor.execute("""
            SELECT v.vehicle_number, p.battery_percentage, p.road_type,
                   p.predicted_range_km, p.predicted_at
            FROM predictions p
            JOIN vehicles v ON p.vehicle_id = v.id
            WHERE p.predicted_by = %s
            ORDER BY p.predicted_at DESC, p.id DESC
        """, (session["user_id"],))
        predictions = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(predictions)

    payload = request.get_json(silent=True) or {}
    vehicle_number = str(payload.get("vehicle_number", "")).strip()
    road_type = str(payload.get("road_type", "")).strip().title()
    try:
        battery = float(payload.get("battery_percentage"))
    except (TypeError, ValueError):
        battery = -1

    if (not vehicle_number or road_type not in {"City", "Highway"}
            or not 0 <= battery <= 100):
        cursor.close()
        connection.close()
        return jsonify({
            "error": "Select a vehicle, City or Highway, and a battery value from 0 to 100"
        }), 400

    cursor.execute("""
        SELECT v.id, v.battery_capacity,
               vr.battery_percentage AS latest_battery,
               vr.remaining_range_km
        FROM vehicles v
        LEFT JOIN vehicle_readings vr ON vr.id = (
            SELECT MAX(vr2.id) FROM vehicle_readings vr2
            WHERE vr2.vehicle_id = v.id
        )
        WHERE v.vehicle_number = %s AND v.assigned_driver_id = %s
    """, (vehicle_number, session["user_id"]))
    vehicle = cursor.fetchone()
    if not vehicle:
        cursor.close()
        connection.close()
        return jsonify({"error": "Vehicle is not assigned to this driver"}), 403

    latest_battery = float(vehicle["latest_battery"] or 0)
    latest_range = float(vehicle["remaining_range_km"] or 0)
    # Scale the latest measured range when available.  This keeps predictions
    # useful with replacement datasets; an ML model can replace this block later.
    predicted_range = (battery / latest_battery * latest_range
                       if latest_battery > 0 and latest_range > 0
                       else battery * 3.2)
    # City traffic generally reduces usable range compared with highway travel.
    # Keep the adjustment here (rather than in the browser) so saved predictions
    # always match the returned value.
    if road_type == "City":
        predicted_range *= 0.85
    predicted_range = round(predicted_range, 2)

    cursor.execute("""
        INSERT INTO predictions
            (vehicle_id, battery_percentage, road_type, predicted_range_km, predicted_by)
        VALUES (%s, %s, %s, %s, %s)
    """, (vehicle["id"], battery, road_type, predicted_range, session["user_id"]))
    connection.commit()
    cursor.close()
    connection.close()
    return jsonify({
        "vehicle_number": vehicle_number,
        "battery_percentage": battery,
        "road_type": road_type,
        "predicted_range_km": predicted_range,
        "status": "Completed"
    }), 201



@app.route("/api/dashboard")
@admin_api_required
def dashboard_api():

    connection = get_connection()
    cursor = connection.cursor()

    # Total vehicles
    cursor.execute("""
        SELECT COUNT(*)
        FROM vehicles
    """)
    total_vehicles = cursor.fetchone()[0]


    # Garage vehicles
    cursor.execute("""
        SELECT COUNT(*)
        FROM vehicles
        WHERE status = 'garage'
    """)
    garage_vehicles = cursor.fetchone()[0]


    # Charging vehicles
    cursor.execute("""
        SELECT COUNT(*)
        FROM vehicles
        WHERE status = 'charging'
    """)
    charging_vehicles = cursor.fetchone()[0]


    # Running vehicles
    cursor.execute("""
        SELECT COUNT(*)
        FROM vehicles
        WHERE status = 'running'
    """)
    running_vehicles = cursor.fetchone()[0]


    cursor.close()
    connection.close()


    return jsonify({

        "total_vehicles": total_vehicles,

        "garage_vehicles": garage_vehicles,

        "charging_vehicles": charging_vehicles,

        "running_vehicles": running_vehicles

    })


@app.route("/api/admin-alerts")
@admin_api_required
def admin_alerts_api():
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT v.vehicle_number, v.make, v.model,
               vr.battery_percentage, vr.recorded_at
        FROM vehicles v
        JOIN vehicle_readings vr ON vr.id = (
            SELECT MAX(vr2.id)
            FROM vehicle_readings vr2
            WHERE vr2.vehicle_id = v.id
        )
        WHERE vr.battery_percentage < 20
        ORDER BY vr.battery_percentage ASC, vr.recorded_at DESC
    """)
    low_battery = cursor.fetchall()

    cursor.execute("""
        SELECT v.vehicle_number,
               COALESCE(u.name, 'Unknown Driver') AS driver_name,
               vr.speed, vr.speed_limit, vr.recorded_at
        FROM vehicle_readings vr
        JOIN vehicles v ON vr.vehicle_id = v.id
        LEFT JOIN users u ON v.assigned_driver_id = u.id
        WHERE vr.driving_behaviour = 'Rash Driving'
        ORDER BY vr.recorded_at DESC
        LIMIT 20
    """)
    rash_driving = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify({
        "low_battery": low_battery,
        "rash_driving": rash_driving,
        "total": len(low_battery) + len(rash_driving)
    })
@app.route("/api/vehicles")
@admin_api_required
def vehicles_api():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    filter_sql, filter_params = date_filter("vr.recorded_at")
    company = request.args.get("company", "").strip()
    if company:
        filter_sql += " AND v.make = %s"
        filter_params.append(company)

    cursor.execute("""
        SELECT
            v.vehicle_number,
            v.make,
            v.model,

            u.name AS driver_name,

            vr.battery_percentage,
            vr.battery_temperature,
            vr.speed,
            vr.city,
            vr.remaining_range_km,
            vr.electricity_consumed,
            vr.charging_status,
            vr.road_type,
            vr.traffic_condition,
            vr.weather,
            vr.outside_temperature_c,
            vr.distance_travelled_km,
            vr.energy_consumption_kwh_per_100km,
            vr.electricity_charged_kwh,

            v.status

        FROM vehicles v

        LEFT JOIN users u
            ON v.assigned_driver_id = u.id

        LEFT JOIN vehicle_readings vr
            ON vr.id = (
                SELECT MAX(vr2.id)
                FROM vehicle_readings vr2
            WHERE vr2.vehicle_id = v.id
        )

        WHERE 1 = 1
    """ + filter_sql + """
        ORDER BY v.id ASC
    """, filter_params)

    vehicles = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(vehicles)

@app.route("/api/electricity")
@admin_api_required
def electricity_api():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    filter_sql, filter_params = date_filter("vr.recorded_at")
    cursor.execute("""
        SELECT
            v.vehicle_number,
            v.make,
            v.model,

            SUM(vr.distance_travelled_km) AS distance,

            SUM(vr.electricity_consumed) AS electricity,

            AVG(vr.energy_consumption_kwh_per_100km) AS efficiency,

            AVG(vr.battery_percentage) AS battery,

            v.status

        FROM vehicles v

        JOIN vehicle_readings vr
            ON v.id = vr.vehicle_id

        WHERE 1 = 1
    """ + filter_sql + """

        GROUP BY
            v.id,
            v.vehicle_number,
            v.make,
            v.model,
            v.status

        ORDER BY electricity DESC
    """, filter_params)

    data = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(data)


# ==========================================
# ELECTRICITY SUMMARY
# ==========================================

@app.route("/api/electricity-summary")
@admin_api_required
def electricity_summary():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    filter_sql, filter_params = date_filter("recorded_at")

    # --------------------------------------
    # TOTAL ELECTRICITY
    # --------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(SUM(electricity_consumed), 0) AS total_consumption
        FROM vehicle_readings
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    total_consumption = cursor.fetchone()["total_consumption"]


    # --------------------------------------
    # AVERAGE ELECTRICITY PER VEHICLE
    # --------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(
                SUM(electricity_consumed) /
                NULLIF(COUNT(DISTINCT vehicle_id), 0),
                0
            ) AS average_consumption
        FROM vehicle_readings
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    average_consumption = cursor.fetchone()["average_consumption"]


    # --------------------------------------
    # HIGHEST CONSUMING VEHICLE
    # --------------------------------------

    # --------------------------------------
# HIGHEST CONSUMING VEHICLE
# --------------------------------------

    cursor.execute("""
    SELECT
        v.vehicle_number,
        v.make,
        v.model,

        SUM(vr.electricity_consumed) AS electricity,

        SUM(vr.distance_travelled_km) AS distance

    FROM vehicle_readings vr

    JOIN vehicles v
        ON vr.vehicle_id = v.id

    WHERE 1 = 1
    """ + date_filter("vr.recorded_at")[0] + """

    GROUP BY
        v.id,
        v.vehicle_number,
        v.make,
        v.model

    ORDER BY electricity DESC

    LIMIT 1
""", date_filter("vr.recorded_at")[1])

    highest = cursor.fetchone()


    # --------------------------------------
    # FLEET EFFICIENCY
    # km / kWh
    # --------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(SUM(distance_travelled_km), 0) AS total_distance,
            COALESCE(SUM(electricity_consumed), 0) AS total_electricity
        FROM vehicle_readings
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    efficiency_data = cursor.fetchone()

    total_distance = float(efficiency_data["total_distance"] or 0)
    total_electricity = float(efficiency_data["total_electricity"] or 0)

    if total_electricity > 0:
        fleet_efficiency = total_distance / total_electricity
    else:
        fleet_efficiency = 0


    cursor.close()
    connection.close()


    return jsonify({

        "total_consumption":
            float(total_consumption or 0),

        "average_consumption":
            float(average_consumption or 0),

        "highest_consumer":
            highest["vehicle_number"]
            if highest else "--",

        "highest_consumer_make":
            highest["make"]
            if highest else "--",

        "highest_consumer_model":
            highest["model"]
            if highest else "--",

        "highest_consumer_electricity":
            float(highest["electricity"])
            if highest else 0,

        "highest_consumer_distance":
        float(highest["distance"])
        if highest else 0,

        

        "fleet_efficiency":
            float(fleet_efficiency)

    })

@app.route("/api/electricity-analysis")
@admin_api_required
def electricity_analysis():

    connection = get_connection()
    cursor = connection.cursor()

    # ==========================================
    # HIGHEST CONSUMER
    # ==========================================

    filter_sql, filter_params = date_filter("vr.recorded_at")
    cursor.execute("""
        SELECT
            v.vehicle_number,
            SUM(vr.electricity_consumed) AS electricity

        FROM vehicle_readings vr

        JOIN vehicles v
            ON vr.vehicle_id = v.id

        WHERE 1 = 1
    """ + filter_sql + """

        GROUP BY
            v.id,
            v.vehicle_number

        ORDER BY electricity DESC

        LIMIT 1
    """, filter_params)

    highest = cursor.fetchone()


    # ==========================================
    # MOST EFFICIENT VEHICLE
    # ==========================================

    cursor.execute("""
        SELECT
            v.vehicle_number,

            SUM(vr.distance_travelled_km) AS distance,

            SUM(vr.electricity_consumed) AS electricity

        FROM vehicle_readings vr

        JOIN vehicles v
            ON vr.vehicle_id = v.id

        WHERE 1 = 1
    """ + filter_sql + """

        GROUP BY
            v.id,
            v.vehicle_number

        HAVING electricity > 0

        ORDER BY
            distance / electricity DESC

        LIMIT 1
    """, filter_params)

    efficient = cursor.fetchone()


    cursor.close()
    connection.close()


    # ==========================================
    # CALCULATE BEST EFFICIENCY
    # ==========================================

    if efficient:

        best_efficiency = (
            float(efficient["distance"]) /
            float(efficient["electricity"])
        )

    else:

        best_efficiency = 0


    return jsonify({

        "highest_consumer":
            highest["vehicle_number"]
            if highest else "--",

        "highest_usage":
            float(highest["electricity"])
            if highest else 0,

        "most_efficient":
            efficient["vehicle_number"]
            if efficient else "--",

        "best_efficiency":
            best_efficiency

    })

@app.route("/api/maintenance")
@admin_api_required
def maintenance_api():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    filter_sql, filter_params = date_filter("m.maintenance_date")
    cursor.execute("""
        SELECT
            m.id,
            v.vehicle_number,
            v.make,
            v.model,
            m.maintenance_type,
            m.description,
            m.cost,
            m.maintenance_date
        FROM maintenance m
        JOIN vehicles v
            ON m.vehicle_id = v.id
        WHERE 1 = 1
    """ + filter_sql + """
        ORDER BY m.maintenance_date DESC
    """, filter_params)

    maintenance = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(maintenance)
@app.route("/api/maintenance-summary")
@admin_api_required
def maintenance_summary():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    filter_sql, filter_params = date_filter("maintenance_date")

    # ==========================================
    # TOTAL MAINTENANCE RECORDS
    # ==========================================

    cursor.execute("""
        SELECT COUNT(*) AS total_records
        FROM maintenance
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    total_records = cursor.fetchone()["total_records"]


    # ==========================================
    # VEHICLES SERVICED
    # ==========================================

    cursor.execute("""
        SELECT COUNT(DISTINCT vehicle_id) AS vehicles_serviced
        FROM maintenance
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    vehicles_serviced = cursor.fetchone()["vehicles_serviced"]


    # ==========================================
    # TOTAL MAINTENANCE COST
    # ==========================================

    cursor.execute("""
        SELECT COALESCE(SUM(cost), 0) AS total_cost
        FROM maintenance
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    total_cost = cursor.fetchone()["total_cost"]


    # ==========================================
    # VEHICLE WITH MAXIMUM MAINTENANCE
    # ==========================================

    cursor.execute("""
        SELECT
            v.id,
            v.vehicle_number,
            v.make,
            v.model,
            v.status,
            COUNT(m.id) AS maintenance_count,
            SUM(m.cost) AS vehicle_cost,
            MAX(m.maintenance_date) AS last_service

        FROM maintenance m

        JOIN vehicles v
            ON m.vehicle_id = v.id
        WHERE 1 = 1
    """ + date_filter("m.maintenance_date")[0] + """

        GROUP BY
            v.id,
            v.vehicle_number,
            v.make,
            v.model,
            v.status

        ORDER BY maintenance_count DESC

        LIMIT 1
    """, date_filter("m.maintenance_date")[1])

    highest = cursor.fetchone()


    cursor.close()
    connection.close()


    return jsonify({

        "total_records": total_records,

        "vehicles_serviced": vehicles_serviced,

        "total_cost": float(total_cost),

        "high_maintenance_vehicle":
            highest["vehicle_number"]
            if highest else "--",

        "high_maintenance_model":
            highest["model"]
            if highest else "--",

        "maintenance_count":
            highest["maintenance_count"]
            if highest else 0,

        "vehicle_cost":
            float(highest["vehicle_cost"])
            if highest else 0,

        "last_service":
            str(highest["last_service"])
            if highest else "--",

        "vehicle_status":
            highest["status"]
            if highest else "--"

    })
@app.route("/api/revenue")
@admin_api_required
def revenue_api():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    filter_sql, filter_params = date_filter("r.revenue_date")
    distance_filter_sql, distance_filter_params = date_filter("vr.recorded_at")
    cursor.execute("""
        SELECT
            v.vehicle_number,
            v.make,
            v.model,
            COALESCE(u.name, 'Not Assigned') AS driver_name,
            COUNT(r.id) AS trips,
            COALESCE((
                SELECT SUM(vr.distance_travelled_km)
                FROM vehicle_readings vr
                WHERE vr.vehicle_id = v.id
            """ + distance_filter_sql + """
            ), 0) AS distance,
            COALESCE(SUM(r.amount), 0) AS amount
        FROM revenue r
        JOIN vehicles v
            ON r.vehicle_id = v.id
        LEFT JOIN users u ON v.assigned_driver_id = u.id
        WHERE 1 = 1
    """ + filter_sql + """
        GROUP BY v.id, v.vehicle_number, v.make, v.model, u.name
        ORDER BY amount DESC
    """, distance_filter_params + filter_params)

    revenue = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(revenue)


@app.route("/api/revenue-by-make")
@admin_api_required
def revenue_by_make_api():
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    filter_sql, filter_params = date_filter("r.revenue_date")
    cursor.execute("""
        SELECT v.make, COUNT(DISTINCT v.id) AS vehicles,
               COUNT(r.id) AS trips, COALESCE(SUM(r.amount), 0) AS revenue,
               COALESCE(SUM(r.amount) / NULLIF(COUNT(DISTINCT v.id), 0), 0) AS average_per_vehicle
        FROM revenue r
        JOIN vehicles v ON r.vehicle_id = v.id
        WHERE 1 = 1
    """ + filter_sql + """
        GROUP BY v.make
        ORDER BY revenue DESC
    """, filter_params)
    data = cursor.fetchall()
    cursor.close()
    connection.close()
    return jsonify(data)

@app.route("/api/revenue-summary")
@admin_api_required
def revenue_summary():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    filter_sql, filter_params = date_filter("revenue_date")

    # Total revenue
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total_revenue
        FROM revenue
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    total_revenue = cursor.fetchone()["total_revenue"]


    # Vehicle with maximum revenue
    cursor.execute("""
        SELECT
            v.vehicle_number,
            v.make,
            v.model,
            SUM(r.amount) AS revenue
        FROM revenue r
        JOIN vehicles v
            ON r.vehicle_id = v.id
        WHERE 1 = 1
    """ + date_filter("r.revenue_date")[0] + """
        GROUP BY
            v.id,
            v.vehicle_number,
            v.make,
            v.model
        ORDER BY revenue DESC
        LIMIT 1
    """, date_filter("r.revenue_date")[1])

    highest_vehicle = cursor.fetchone()


    # Make with maximum revenue
    cursor.execute("""
        SELECT
            v.make,
            SUM(r.amount) AS revenue
        FROM revenue r
        JOIN vehicles v
            ON r.vehicle_id = v.id
        WHERE 1 = 1
    """ + date_filter("r.revenue_date")[0] + """
        GROUP BY v.make
        ORDER BY revenue DESC
        LIMIT 1
    """, date_filter("r.revenue_date")[1])

    highest_make = cursor.fetchone()


    # Number of revenue records
    cursor.execute("""
        SELECT COUNT(*) AS total_records
        FROM revenue
        WHERE 1 = 1
    """ + filter_sql, filter_params)

    total_records = cursor.fetchone()["total_records"]

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS monthly_revenue,
               COUNT(DISTINCT vehicle_id) AS revenue_vehicles
        FROM revenue
        WHERE 1 = 1
    """ + filter_sql, filter_params)
    monthly = cursor.fetchone()


    cursor.close()
    connection.close()


    return jsonify({

        "total_revenue": float(total_revenue),

        "highest_vehicle":
            highest_vehicle["vehicle_number"]
            if highest_vehicle else "--",

        "highest_vehicle_revenue":
            float(highest_vehicle["revenue"])
            if highest_vehicle else 0,

        "highest_make":
            highest_make["make"]
            if highest_make else "--",

        "highest_make_revenue":
            float(highest_make["revenue"])
            if highest_make else 0,

        "total_records": total_records
        ,"monthly_revenue": float(monthly["monthly_revenue"] or 0)
        ,"revenue_vehicles": monthly["revenue_vehicles"]

    })



# ==========================================
# DRIVER BEHAVIOUR API
# ==========================================

@app.route("/api/driver-behaviour")
@admin_api_required
def driver_behaviour_api():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    filter_sql, filter_params = date_filter("vr.recorded_at")

    cursor.execute("""
        SELECT
            COALESCE(u.name, 'Unknown Driver') AS driver_name,
            v.vehicle_number,
            AVG(vr.speed) AS average_speed,
            AVG(vr.speed_limit) AS speed_limit,
            SUM(CASE WHEN vr.speed > vr.speed_limit THEN 1 ELSE 0 END) AS overspeed_events,
            SUM(CASE WHEN vr.driving_behaviour = 'Rash Driving' THEN 1 ELSE 0 END)
                AS rash_events,
            GREATEST(
                0,
                100
                - (SUM(CASE WHEN vr.speed > vr.speed_limit THEN 1 ELSE 0 END) * 5)
                - (SUM(CASE WHEN vr.driving_behaviour = 'Rash Driving' THEN 1 ELSE 0 END) * 10)
            ) AS safety_score,
            CASE
                WHEN SUM(CASE WHEN vr.speed > vr.speed_limit THEN 1 ELSE 0 END) >= 5
                    OR SUM(CASE WHEN vr.driving_behaviour = 'Rash Driving' THEN 1 ELSE 0 END) >= 3
                    THEN 'High Risk'
                WHEN SUM(CASE WHEN vr.speed > vr.speed_limit THEN 1 ELSE 0 END) > 0
                    OR SUM(CASE WHEN vr.driving_behaviour = 'Rash Driving' THEN 1 ELSE 0 END) > 0
                    THEN 'Needs Attention'
                ELSE 'Safe'
            END AS status
        FROM vehicle_readings vr
        JOIN vehicles v ON vr.vehicle_id = v.id
        LEFT JOIN users u ON v.assigned_driver_id = u.id
        WHERE 1 = 1
    """ + filter_sql + """
        GROUP BY v.id, v.vehicle_number, u.name
        ORDER BY safety_score ASC, overspeed_events DESC
    """, filter_params)

    data = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(data)


@app.route("/api/driving-events")
@admin_api_required
def driving_events_api():

    connection = get_connection()
    cursor = connection.cursor()
    filter_sql, filter_params = date_filter("vr.recorded_at")

    cursor.execute("""
        SELECT
            vr.id AS event_id,
            COALESCE(u.name, 'Unknown Driver') AS driver_name,
            v.vehicle_number,
            CASE
                WHEN vr.driving_behaviour = 'Rash Driving' THEN 'Rash Driving'
                ELSE 'Overspeed'
            END AS event,
            vr.speed,
            vr.speed_limit,
            vr.city,
            vr.recorded_at
        FROM vehicle_readings vr
        JOIN vehicles v ON vr.vehicle_id = v.id
        LEFT JOIN users u ON v.assigned_driver_id = u.id
        WHERE (vr.speed > vr.speed_limit OR vr.driving_behaviour = 'Rash Driving')
    """ + filter_sql + """
        ORDER BY vr.id DESC
    """, filter_params)

    data = cursor.fetchall()
    cursor.close()
    connection.close()

    return jsonify(data)


# ==========================================
# DRIVER BEHAVIOUR SUMMARY
# ==========================================

@app.route("/api/driver-behaviour-summary")
@admin_api_required
def driver_behaviour_summary():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    # --------------------------------------
    # TOTAL DRIVER READINGS
    # --------------------------------------

    cursor.execute("""
        SELECT COUNT(*) AS total_records
        FROM vehicle_readings
    """)

    total_records = cursor.fetchone()["total_records"]


    # --------------------------------------
    # MOST COMMON DRIVING BEHAVIOUR
    # --------------------------------------

    cursor.execute("""
        SELECT
            driving_behaviour,
            COUNT(*) AS behaviour_count

        FROM vehicle_readings

        WHERE driving_behaviour IS NOT NULL
        AND driving_behaviour != ''

        GROUP BY driving_behaviour

        ORDER BY behaviour_count DESC

        LIMIT 1
    """)

    common = cursor.fetchone()


    # --------------------------------------
    # AVERAGE SPEED
    # --------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(AVG(speed), 0) AS average_speed

        FROM vehicle_readings
    """)

    average_speed = cursor.fetchone()["average_speed"]


    # --------------------------------------
    # AVERAGE BATTERY
    # --------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(AVG(battery_percentage), 0)
            AS average_battery

        FROM vehicle_readings
    """)

    average_battery = cursor.fetchone()["average_battery"]


    cursor.close()
    connection.close()


    return jsonify({

        "total_records":
            total_records,

        "common_behaviour":
            common["driving_behaviour"]
            if common else "--",

        "average_speed":
            float(average_speed or 0),

        "average_battery":
            float(average_battery or 0)

    })


@app.route("/api/driver-behaviour-metrics")
@admin_api_required
def driver_behaviour_metrics():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    filter_sql, filter_params = date_filter("recorded_at")

    cursor.execute("""
        SELECT COUNT(DISTINCT assigned_driver_id) AS total_drivers
        FROM vehicles
        WHERE assigned_driver_id IS NOT NULL
    """)
    total_drivers = cursor.fetchone()["total_drivers"]

    cursor.execute("""
        SELECT COUNT(*) AS overspeed_events
        FROM vehicle_readings
        WHERE speed > speed_limit
        """ + filter_sql, filter_params)
    overspeed_events = cursor.fetchone()["overspeed_events"]

    cursor.execute("""
        SELECT COUNT(*) AS rash_events
        FROM vehicle_readings
        WHERE driving_behaviour = 'Rash Driving'
        """ + filter_sql, filter_params)
    rash_events = cursor.fetchone()["rash_events"]

    cursor.execute("""
        SELECT COALESCE(AVG(driver_score), 0) AS average_safety_score
        FROM (
            SELECT GREATEST(
                0,
                100
                - (SUM(CASE WHEN speed > speed_limit THEN 1 ELSE 0 END) * 5)
                - (SUM(CASE WHEN driving_behaviour = 'Rash Driving' THEN 1 ELSE 0 END) * 10)
            ) AS driver_score
            FROM vehicle_readings
            WHERE 1 = 1
        """ + filter_sql + """
            GROUP BY vehicle_id
        ) scores
    """, filter_params)
    average_safety_score = cursor.fetchone()["average_safety_score"]

    cursor.close()
    connection.close()

    return jsonify({
        "total_drivers": total_drivers,
        "overspeed_events": overspeed_events,
        "rash_events": rash_events,
        "average_safety_score": float(average_safety_score or 0)
    })

@app.route("/api/high-risk-driver")
@admin_api_required
def high_risk_driver():

    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    filter_sql, filter_params = date_filter("vr.recorded_at")

    cursor.execute("""
        SELECT
            v.vehicle_number,
            v.make,
            v.model,
            u.name AS driver_name,

            AVG(vr.speed) AS average_speed,
            AVG(vr.speed_limit) AS speed_limit,

            SUM(
                CASE
                    WHEN vr.speed > vr.speed_limit THEN 1
                    ELSE 0
                END
            ) AS overspeed_events,

            SUM(
                CASE
                    WHEN vr.driving_behaviour = 'Rash Driving'
                    THEN 1
                    ELSE 0
                END
            ) AS rash_events

        FROM vehicle_readings vr

        JOIN vehicles v
            ON vr.vehicle_id = v.id

        LEFT JOIN users u
            ON v.assigned_driver_id = u.id
        WHERE 1 = 1
    """ + filter_sql + """

        GROUP BY
            v.id,
            v.vehicle_number,
            v.make,
            v.model,
            u.name

        ORDER BY
            overspeed_events DESC,
            average_speed DESC

        LIMIT 1
    """, filter_params)

    driver = cursor.fetchone()

    cursor.close()
    connection.close()

    if not driver:
        return jsonify({
            "driver_name": "--",
            "vehicle_number": "--",
            "make": "--",
            "model": "--",
            "average_speed": 0,
            "overspeed_events": 0,
            "rash_events": 0
        })

    return jsonify({

        "driver_name":
            driver["driver_name"] or "Unknown Driver",

        "vehicle_number":
            driver["vehicle_number"],

        "make":
            driver["make"],

        "model":
            driver["model"],

        "average_speed":
            float(driver["average_speed"] or 0),

        "speed_limit":
            float(driver["speed_limit"] or 0),

        "overspeed_events":
            int(driver["overspeed_events"] or 0),

        "rash_events":
            int(driver["rash_events"] or 0)

    })

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=False)
