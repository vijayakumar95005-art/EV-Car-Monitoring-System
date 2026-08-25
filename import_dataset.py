"""Replace fleet data. Usage: python import_dataset.py DATASET.xlsx --replace"""

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from werkzeug.security import generate_password_hash

from database import get_connection


REQUIRED_COLUMNS = {
    "Driver Name", "Email", "Password", "Company", "Car Model",
    "Battery Capacity (kWh)", "Rated Range (km)", "Motor Power (kW)",
    "Kerb Weight (kg)", "Max Torque (Nm)", "Length (mm)", "Width (mm)",
    "Height (mm)", "Wheelbase (mm)", "Date & Time", "Battery (%)",
    "Instant Speed (km/h)", "Speed Limit (km/h)", "Driving Behaviour",
    "Vehicle Status", "Charging Status", "City", "Road Type",
    "Distance Travelled (km)", "Energy Consumed (kWh)",
    "Efficiency (kWh/100km)", "Electricity Charged (kWh)",
    "Total Revenue (INR)", "Maintenance Status", "Maintenance Cost (INR)",
    "Remaining Range (km)",
}


def scalar(row, column):
    item = row[column]
    return item.item() if hasattr(item, "item") else item


def main():
    parser = argparse.ArgumentParser(description="Replace EV fleet data from a dataset")
    parser.add_argument("dataset", help="Path to .xlsx, .xls, or .csv dataset")
    parser.add_argument("--replace", action="store_true", help="Confirm destructive replacement")
    args = parser.parse_args()
    if not args.replace:
        parser.error("--replace is required because this clears fleet data")

    path = Path(args.dataset)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")
    data = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path, sheet_name="EV Fleet Data")

    temp_column = next((column for column in data.columns if column.startswith("Battery Temp")), None)
    if temp_column is None:
        raise ValueError("Dataset is missing a Battery Temp column")
    data = data.rename(columns={temp_column: "Battery Temperature"})
    missing = REQUIRED_COLUMNS.difference(data.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")

    data["recorded_at"] = pd.to_datetime(data["Date & Time"], errors="raise")
    data["status"] = data["Vehicle Status"].map({
        "Running": "running", "Parked": "garage", "Charging": "charging", "Maintenance": "garage",
    }).fillna("garage")
    data["behaviour"] = data["Driving Behaviour"].replace({"Aggressive": "Rash Driving", "Normal": "Normal"})
    drivers = data.sort_values("Email").drop_duplicates("Email").copy()
    drivers["vehicle_number"] = [f"EV{index:03d}" for index in range(1, len(drivers) + 1)]
    vehicle_by_email = drivers.set_index("Email")["vehicle_number"].to_dict()

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT email FROM users WHERE role = 'admin'")
        conflicts = sorted({row["email"] for row in cursor.fetchall()}.intersection(set(drivers["Email"])))
        if conflicts:
            raise ValueError("Dataset driver email conflicts with admin: " + ", ".join(conflicts))

        cursor.execute("SHOW COLUMNS FROM vehicle_readings LIKE 'speed_limit'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE vehicle_readings ADD speed_limit DECIMAL(6,2) NULL AFTER speed")
        vehicle_columns = {
            "rated_range": "DECIMAL(10,2)",
            "motor_power": "DECIMAL(10,2)",
            "kerb_weight": "DECIMAL(10,2)",
            "max_torque": "DECIMAL(10,2)",
            "vehicle_length": "DECIMAL(10,2)",
            "vehicle_width": "DECIMAL(10,2)",
            "vehicle_height": "DECIMAL(10,2)",
            "wheelbase": "DECIMAL(10,2)",
        }
        for column, definition in vehicle_columns.items():
            cursor.execute(f"SHOW COLUMNS FROM vehicles LIKE '{column}'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE vehicles ADD {column} {definition} NULL")

        tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        for table in ("predictions", "maintenance", "revenue", "vehicle_readings", "driver_behaviour", "vehicles", "users"):
            cursor.execute(f"CREATE TABLE backup_{tag}_{table} AS SELECT * FROM {table}")
        for table in ("predictions", "maintenance", "revenue", "vehicle_readings", "driver_behaviour", "vehicles"):
            cursor.execute(f"DELETE FROM {table}")
        cursor.execute("DELETE FROM users WHERE role = 'driver'")
        connection.commit()

        cursor.close()
        cursor = connection.cursor()
        cursor.executemany("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, 'driver')", [
            (scalar(row, "Driver Name"), scalar(row, "Email"), generate_password_hash(str(scalar(row, "Password"))))
            for _, row in drivers.iterrows()
        ])
        connection.commit()
        cursor.execute("SELECT id, email FROM users WHERE role = 'driver'")
        driver_ids = {email: user_id for user_id, email in cursor.fetchall()}
        cursor.executemany("""
            INSERT INTO vehicles
                (vehicle_number, make, model, battery_capacity, rated_range, motor_power,
                 kerb_weight, max_torque, vehicle_length, vehicle_width, vehicle_height,
                 wheelbase, status, assigned_driver_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [
            (vehicle_by_email[scalar(row, "Email")], scalar(row, "Company"), scalar(row, "Car Model"),
             scalar(row, "Battery Capacity (kWh)"), scalar(row, "Rated Range (km)"),
             scalar(row, "Motor Power (kW)"), scalar(row, "Kerb Weight (kg)"),
             scalar(row, "Max Torque (Nm)"), scalar(row, "Length (mm)"),
             scalar(row, "Width (mm)"), scalar(row, "Height (mm)"), scalar(row, "Wheelbase (mm)"),
             scalar(row, "status"), driver_ids[scalar(row, "Email")])
            for _, row in drivers.iterrows()
        ])
        connection.commit()
        cursor.execute("SELECT id, vehicle_number FROM vehicles")
        vehicle_ids = {number: vehicle_id for vehicle_id, number in cursor.fetchall()}

        readings, revenue, maintenance = [], [], []
        for _, row in data.iterrows():
            vehicle_id = vehicle_ids[vehicle_by_email[scalar(row, "Email")]]
            recorded_at = scalar(row, "recorded_at").to_pydatetime()
            readings.append((vehicle_id, scalar(row, "Battery (%)"), scalar(row, "Battery Temperature"),
                scalar(row, "Instant Speed (km/h)"), scalar(row, "Speed Limit (km/h)"), scalar(row, "City"),
                scalar(row, "Energy Consumed (kWh)"), scalar(row, "Charging Status"), scalar(row, "Road Type"),
                None, None, scalar(row, "Distance Travelled (km)"), scalar(row, "Efficiency (kWh/100km)"),
                scalar(row, "Electricity Charged (kWh)"), scalar(row, "Remaining Range (km)"), scalar(row, "behaviour"), recorded_at))
            revenue.append((vehicle_id, scalar(row, "Total Revenue (INR)"), recorded_at.date()))
            if scalar(row, "Maintenance Status") == "Required":
                maintenance.append((vehicle_id, "Maintenance Required", "Imported from fleet dataset",
                    scalar(row, "Maintenance Cost (INR)"), recorded_at.date()))

        cursor.executemany("""
            INSERT INTO vehicle_readings (vehicle_id, battery_percentage, battery_temperature, speed, speed_limit, city,
            electricity_consumed, charging_status, road_type, traffic_condition, weather, distance_travelled_km,
            energy_consumption_kwh_per_100km, electricity_charged_kwh, remaining_range_km, driving_behaviour, recorded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, readings)
        cursor.executemany("INSERT INTO revenue (vehicle_id, amount, revenue_date) VALUES (%s, %s, %s)", revenue)
        if maintenance:
            cursor.executemany("""
                INSERT INTO maintenance (vehicle_id, maintenance_type, description, cost, maintenance_date)
                VALUES (%s, %s, %s, %s, %s)
            """, maintenance)
        connection.commit()
        print(f"Imported {len(drivers)} drivers, {len(readings)} readings, {len(revenue)} revenue logs, and {len(maintenance)} maintenance records.")
        print(f"Backup tables prefix: backup_{tag}_")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
