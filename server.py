import os
import re
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Flask, flash, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "employee-management-secret-key"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "employee.db")


def get_database_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def create_tables():
    connection = get_database_connection()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullname TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                department TEXT NOT NULL,
                salary REAL NOT NULL,
                joining_date TEXT NOT NULL,
                address TEXT
            );
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Present',
                UNIQUE(employee_id, attendance_date),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            );
            CREATE TABLE IF NOT EXISTS employee_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                skill TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 60,
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );
            """
        )
        employee_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(employees)")
        }
        if "designation" not in employee_columns:
            connection.execute("ALTER TABLE employees ADD COLUMN designation TEXT NOT NULL DEFAULT ''")
        connection.commit()
    finally:
        connection.close()


@app.context_processor
def inject_template_values():
    return {
        "theme": request.cookies.get("theme", "light"),
        "username": session.get("username"),
    }


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def read_employee_form():
    return {
        field: request.form.get(field, "").strip()
        for field in (
            "name", "email", "phone", "department", "designation", "salary", "joining_date", "address", "skills"
        )
    }


def save_employee_skills(connection, employee_id, skills_text):
    connection.execute("DELETE FROM employee_skills WHERE employee_id = ?", (employee_id,))
    skills = [skill.strip() for skill in skills_text.split(",") if skill.strip()]
    connection.executemany(
        "INSERT INTO employee_skills (employee_id, skill, level) VALUES (?, ?, ?)",
        [(employee_id, skill, 60) for skill in skills[:12]],
    )


def validate_employee_form(employee):
    required_fields = (
        "name", "email", "phone", "department", "salary", "joining_date"
    )
    if any(not employee[field] for field in required_fields):
        return None, "Please fill all required fields!"
    try:
        employee["salary"] = float(employee["salary"])
    except (TypeError, ValueError):
        return None, "Salary must be a valid number greater than 0."
    if employee["salary"] <= 0:
        return None, "Salary must be greater than 0."

    if not employee["joining_date"]:
        return None, "Joining date is required."
    try:
        joining_date = datetime.strptime(employee["joining_date"], "%Y-%m-%d").date()
    except ValueError:
        return None, "Enter a valid joining date."
    if joining_date > date.today():
        return None, "Joining date cannot be in the future."

    return employee, None


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/set-theme/<theme>")
def set_theme(theme):
    selected_theme = theme if theme in {"light", "dark"} else "light"
    response = make_response(redirect(request.referrer or url_for("home")))
    response.set_cookie("theme", selected_theme, max_age=60 * 60 * 24 * 365)
    return response


@app.route("/employee")
def employees():
    connection = get_database_connection()
    try:
        employee_list = connection.execute(
            """
            WITH unique_employees AS (
                SELECT employee.*
                FROM employees AS employee
                WHERE employee.id = (
                    SELECT MAX(newer.id)
                    FROM employees AS newer
                    WHERE LOWER(TRIM(newer.email)) = LOWER(TRIM(employee.email))
                )
            )
            SELECT
                unique_employees.*,
                COALESCE(GROUP_CONCAT(employee_skills.skill, ', '), '') AS skills
            FROM unique_employees
            LEFT JOIN employee_skills
                ON employee_skills.employee_id = unique_employees.id
            GROUP BY unique_employees.id
            ORDER BY unique_employees.id DESC
            """
        ).fetchall()
    finally:
        connection.close()
    return render_template("employee.html", employees=employee_list, total=len(employee_list))


@app.route("/employee/<int:id>")
def employee_profile(id):
    connection = get_database_connection()
    try:
        employee = connection.execute("SELECT * FROM employees WHERE id = ?", (id,)).fetchone()
        skills = connection.execute(
            "SELECT skill, level FROM employee_skills WHERE employee_id = ? ORDER BY id",
            (id,),
        ).fetchall()
    finally:
        connection.close()
    if employee is None:
        flash("Employee not found.", "warning")
        return redirect(url_for("employees"))
    return render_template("skill.html", employee=employee, skills=skills, ai_suggestions=None)


@app.post("/employee/<int:id>/analyze-skills")
def analyze_skills(id):
    connection = get_database_connection()
    try:
        employee = connection.execute("SELECT * FROM employees WHERE id = ?", (id,)).fetchone()
        skills = connection.execute(
            "SELECT skill, level FROM employee_skills WHERE employee_id = ? ORDER BY id",
            (id,),
        ).fetchall()
    finally:
        connection.close()

    if employee is None:
        flash("Employee not found.", "warning")
        return redirect(url_for("employees"))

    current_skills = {skill["skill"].strip().lower() for skill in skills}
    suggestions_by_department = {
        "development": ["SQL", "REST APIs", "Docker"],
        "engineering": ["System Design", "Testing", "Docker"],
        "design": ["User Research", "Prototyping", "Accessibility"],
        "marketing": ["Analytics", "SEO", "Content Strategy"],
        "human resources": ["People Analytics", "Interviewing", "Employment Law"],
    }
    department = employee["department"].strip().lower()
    suggestions = [
        suggestion
        for suggestion in suggestions_by_department.get(
            department, ["Communication", "Project Management", "Data Analysis"]
        )
        if suggestion.lower() not in current_skills
    ]
    return render_template(
        "skill.html",
        employee=employee,
        skills=skills,
        ai_suggestions=suggestions[:3],
    )


@app.post("/employee/<int:id>/skills")
def update_employee_skills(id):
    skills_text = request.form.get("skills", "")
    connection = get_database_connection()
    try:
        employee = connection.execute("SELECT id FROM employees WHERE id = ?", (id,)).fetchone()
        if employee is None:
            flash("Employee not found.", "warning")
            return redirect(url_for("employees"))
        save_employee_skills(connection, id, skills_text)
        connection.commit()
    finally:
        connection.close()
    flash("Skills updated successfully!", "success")
    return redirect(url_for("employee_profile", id=id))


@app.route("/add-employee", methods=["GET", "POST"])
def add_employee():
    if request.method == "GET":
        return render_template("add-employee.html")

    employee, error = validate_employee_form(read_employee_form())
    if error:
        flash(error, "danger")
        return render_template("add-employee.html")

    connection = get_database_connection()
    try:
        connection.execute(
            """
            INSERT INTO employees
                (name, email, phone, department, designation, salary, joining_date, address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(employee[field] for field in (
                "name", "email", "phone", "department", "designation", "salary", "joining_date", "address"
            )),
        )
        employee_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        save_employee_skills(connection, employee_id, employee["skills"])
        connection.commit()
    except sqlite3.Error as error:
        connection.rollback()
        flash(f"Database error: {error}", "danger")
        return render_template("add-employee.html")
    finally:
        connection.close()

    flash("Employee added successfully!", "success")
    return redirect(url_for("employees"))


@app.route("/edit-employee/<int:id>", methods=["GET", "POST"])
def edit_employee(id):
    connection = get_database_connection()
    try:
        employee = connection.execute(
            "SELECT * FROM employees WHERE id = ?", (id,)
        ).fetchone()
        skills = connection.execute(
            "SELECT skill FROM employee_skills WHERE employee_id = ? ORDER BY id",
            (id,),
        ).fetchall()
    finally:
        connection.close()

    if employee is None:
        flash("Employee not found!", "warning")
        return redirect(url_for("employees"))

    if request.method == "GET":
        skills_text = ", ".join(skill["skill"] for skill in skills)
        return render_template(
            "edit employee.html", employee=employee, skills_text=skills_text
        )

    updated_employee, error = validate_employee_form(read_employee_form())
    if error:
        flash(error, "danger")
        return redirect(url_for("edit_employee", id=id))

    connection = get_database_connection()
    try:
        connection.execute(
            """
            UPDATE employees
            SET name = ?, email = ?, phone = ?, department = ?, designation = ?, salary = ?,
                joining_date = ?, address = ?
            WHERE id = ?
            """,
            tuple(updated_employee[field] for field in (
                "name", "email", "phone", "department", "designation", "salary", "joining_date", "address"
            )) + (id,),
        )
        save_employee_skills(connection, id, updated_employee["skills"])
        connection.commit()
    except sqlite3.Error as error:
        connection.rollback()
        flash(f"Database error: {error}", "danger")
        return redirect(url_for("edit_employee", id=id))
    finally:
        connection.close()

    flash("Employee details updated successfully!", "success")
    return redirect(url_for("employees"))


@app.post("/delete-employee/<int:id>")
def delete_employee(id):
    connection = get_database_connection()
    try:
        connection.execute("DELETE FROM employees WHERE id = ?", (id,))
        connection.commit()
    finally:
        connection.close()
    flash("Employee record deleted successfully!", "success")
    return redirect(url_for("employees"))


@app.route("/search")
def search():
    query = request.args.get("query", "").strip()
    employees_found = []
    if query:
        search_value = f"%{query}%"
        connection = get_database_connection()
        try:
            employees_found = connection.execute(
                """
                SELECT * FROM employees
                WHERE name LIKE ? OR email LIKE ? OR phone LIKE ?
                   OR department LIKE ? OR address LIKE ?
                ORDER BY id DESC
                """,
                (search_value,) * 5,
            ).fetchall()
        finally:
            connection.close()
    return render_template("search.html", employees=employees_found, query=query)


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    selected_date = request.values.get("attendance_date", date.today().isoformat())
    connection = get_database_connection()
    try:
        if request.method == "POST":
            employees = connection.execute("SELECT id FROM employees").fetchall()
            for employee in employees:
                status = request.form.get(f"status_{employee['id']}", "Absent")
                if status not in {"Present", "Absent", "Leave"}:
                    status = "Absent"
                connection.execute(
                    """
                    INSERT INTO attendance (employee_id, attendance_date, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT(employee_id, attendance_date)
                    DO UPDATE SET status = excluded.status
                    """,
                    (employee["id"], selected_date, status),
                )
            connection.commit()
            flash("Attendance saved successfully!", "success")

        attendance_rows = connection.execute(
            """
            SELECT employees.*, COALESCE(attendance.status, 'Absent') AS attendance_status
            FROM employees
            LEFT JOIN attendance
                ON attendance.employee_id = employees.id
               AND attendance.attendance_date = ?
            ORDER BY employees.name COLLATE NOCASE
            """,
            (selected_date,),
        ).fetchall()
    finally:
        connection.close()
    return render_template(
        "attendence.html",
        employees=attendance_rows,
        selected_date=selected_date,
    )


@app.get("/departments")
def departments():
    connection = get_database_connection()
    try:
        department_list = connection.execute(
            "SELECT department, COUNT(*) AS total, COALESCE(SUM(salary), 0) AS payroll FROM employees GROUP BY department ORDER BY total DESC"
        ).fetchall()
    finally:
        connection.close()
    return render_template("departments.html", departments=department_list)


@app.get("/reports")
def reports():
    connection = get_database_connection()
    try:
        department_counts = connection.execute(
            "SELECT department, COUNT(*) AS total, COALESCE(AVG(salary), 0) AS average_salary FROM employees GROUP BY department ORDER BY total DESC"
        ).fetchall()
    finally:
        connection.close()
    return render_template("reports.html", departments=department_counts)


@app.get("/settings")
def settings():
    return render_template("settings.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    fullname = request.form.get("fullname", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not fullname or not username or not password:
        flash("Please fill all fields!", "danger")
        return render_template("register.html")

    connection = get_database_connection()
    try:
        connection.execute(
            "INSERT INTO users (fullname, username, password) VALUES (?, ?, ?)",
            (fullname, username, generate_password_hash(password)),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        flash("Username already exists!", "danger")
        return render_template("register.html")
    finally:
        connection.close()

    flash("Registration successful! Please log in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Please enter both username and password!", "danger")
        return render_template("login.html")

    connection = get_database_connection()
    try:
        user = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    finally:
        connection.close()

    if user and check_password_hash(user["password"], password):
        session["username"] = user["username"]
        session["fullname"] = user["fullname"]
        flash(f"Welcome back, {user['fullname']}!", "success")
        return redirect(url_for("home"))

    flash("Invalid username or password!", "danger")
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


create_tables()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
