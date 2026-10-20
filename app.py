
from flask import Flask, send_file, request, session, render_template, redirect
import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import jsonify

load_dotenv()

app = Flask(__name__)

app.config["UPLOAD_FOLDER"] = os.path.join(
    app.root_path, "static", "profile_photos"
)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.secret_key = os.getenv("FLASK_SECRET_KEY")

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        use_pure=True
    )

@app.route("/")
def home():
    return send_file("home.html")

@app.route("/settings")
def settings_page():
    if "user_id" not in session:
        return redirect("/login-page")

    return send_file("settings.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login-page")

    return send_file("index.html")

@app.route("/register-page")
def register_page():
    return send_file("register.html")

@app.route("/login-page")
def login_page():
    return send_file("login.html")

@app.route("/db-test")
def db_test():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE();")
        result = cursor.fetchone()

        return f"Database connected successfully: {result[0]}"

    except mysql.connector.Error as error:
        return f"Database connection failed: {error}", 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not email or not password:
        return {"message": "All fields are required."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )

        if cursor.fetchone():
            return {"message": "Email already registered."}, 409

        hashed_password = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (%s, %s, %s)
            """,
            (name, email, hashed_password)
        )

        conn.commit()

        return {"message": "Registration successful."}, 201

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {"message": "Email and password are required."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT user_id, name, email, password FROM users WHERE email = %s",
            (email,)
        )

        user = cursor.fetchone()

        if not user:
            return {"message": "Invalid email or password."}, 401

        if not check_password_hash(user["password"], password):
            return {"message": "Invalid email or password."}, 401

        session["user_id"] = user["user_id"]
        session["name"] = user["name"]
        session["email"] = user["email"]

        return {
            "message": "Login successful.",
            "user": {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"]
            }
        }, 200

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")


@app.route("/me")
def get_current_user():
    if "user_id" not in session:
        return {"message": "Not logged in."}, 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id, name, email, profile_photo
            FROM users
            WHERE user_id = %s
            """,
            (session["user_id"],)
        )

        user = cursor.fetchone()

        if not user:
            session.clear()
            return {"message": "User not found."}, 404

        return {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "photo_url": (
                f"/static/profile_photos/{user['profile_photo']}"
                if user["profile_photo"] else None
            )
        }, 200

    except mysql.connector.Error:
        return {"message": "Unable to load profile."}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/profile", methods=["PUT"])
def update_profile():
    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()

    if not name:
        return {"message": "Name is required."}, 400

    if len(name) > 100:
        return {"message": "Name must be 100 characters or fewer."}, 400

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"message": "Please enter a valid email address."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s AND user_id != %s",
            (email, session["user_id"])
        )

        if cursor.fetchone():
            return {"message": "This email is already in use."}, 409

        cursor.execute(
            "UPDATE users SET name = %s, email = %s WHERE user_id = %s",
            (name, email, session["user_id"])
        )

        conn.commit()
        session["name"] = name

        return {
            "message": "Profile updated successfully.",
            "name": name,
            "email": email
        }, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()
        return {"message": "Unable to update profile."}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/change-password", methods=["POST"])
def change_password():
    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}

    current_password = data.get("currentPassword", "")
    new_password = data.get("newPassword", "")
    confirm_password = data.get("confirmPassword", "")

    if not current_password or not new_password or not confirm_password:
        return {"message": "All password fields are required."}, 400

    if len(new_password) < 8:
        return {"message": "New password must be at least 8 characters."}, 400

    if new_password != confirm_password:
        return {"message": "New passwords do not match."}, 400

    if current_password == new_password:
        return {"message": "New password must differ from current password."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT password FROM users WHERE user_id = %s",
            (session["user_id"],)
        )
        user = cursor.fetchone()

        if not user:
            return {"message": "User not found."}, 404

        if not check_password_hash(user["password"], current_password):
            return {"message": "Current password is incorrect."}, 400

        hashed_password = generate_password_hash(new_password)

        cursor.execute(
            "UPDATE users SET password = %s WHERE user_id = %s",
            (hashed_password, session["user_id"])
        )
        conn.commit()

        return {"message": "Password changed successfully."}, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()
        return {"message": "Unable to change password. Please try again."}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/profile/email", methods=["PUT"])
def update_profile_email():
    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"message": "Please enter a valid email address."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s AND user_id != %s",
            (email, session["user_id"])
        )

        if cursor.fetchone():
            return {"message": "This email is already in use."}, 409

        cursor.execute(
            "UPDATE users SET email = %s WHERE user_id = %s",
            (email, session["user_id"])
        )
        conn.commit()

        return {"message": "Email updated successfully."}, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()
        return {"message": "Unable to update email. Please try again."}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/profile/photo", methods=["POST"])
def upload_profile_photo():
    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    if "photo" not in request.files:
        return {"message": "Please choose a photo."}, 400

    photo = request.files["photo"]

    if not photo.filename:
        return {"message": "Please choose a photo."}, 400

    allowed_extensions = {"png", "jpg", "jpeg", "webp"}
    extension = photo.filename.rsplit(".", 1)[-1].lower()

    if "." not in photo.filename or extension not in allowed_extensions:
        return {"message": "Only PNG, JPG, JPEG and WebP images are allowed."}, 400

    import uuid
    from PIL import Image

    try:
        image = Image.open(photo.stream)
        image.verify()
        photo.stream.seek(0)
    except Exception:
        return {"message": "Invalid image file."}, 400

    filename = f"{session['user_id']}_{uuid.uuid4().hex}.{extension}"
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    try:
        photo.save(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET profile_photo = %s WHERE user_id = %s",
            (filename, session["user_id"])
        )
        conn.commit()

        return {
            "message": "Profile photo uploaded successfully.",
            "photo_url": f"/static/profile_photos/{filename}"
        }, 200

    except Exception:
        if "conn" in locals():
            conn.rollback()
        if os.path.exists(filepath):
            os.remove(filepath)
        return {"message": "Unable to save profile photo."}, 500

    finally:
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals():
            conn.close()

# PROJECT APIs

@app.route("/api/projects", methods=["GET"])
def get_projects():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT project_id, project_name
            FROM projects
            WHERE user_id = %s
            ORDER BY project_name
            """,
            (session["user_id"],)
        )

        projects = cursor.fetchall()

        return {"projects": projects}, 200

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@app.route("/api/projects", methods=["POST"])
def create_project():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}
    project_name = data.get("project_name", "").strip()

    if not project_name:
        return {"message": "Project name is required."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO projects (user_id, project_name)
            VALUES (%s, %s)
            """,
            (
                session["user_id"],
                project_name
            )
        )

        conn.commit()

        return {
            "message": "Project created successfully.",
            "project_id": cursor.lastrowid,
            "project_name": project_name
        }, 201

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # First verify that this project belongs to logged-in user
        cursor.execute(
            """
            SELECT project_id
            FROM projects
            WHERE project_id = %s
            AND user_id = %s
            """,
            (
                project_id,
                session["user_id"]
            )
        )

        project = cursor.fetchone()

        if not project:
            return {"message": "Project not found."}, 404

        # Move this user's tasks to No project
        cursor.execute(
            """
            UPDATE tasks
            SET project_id = NULL
            WHERE project_id = %s
            AND user_id = %s
            """,
            (
                project_id,
                session["user_id"]
            )
        )

        # Delete only this user's project
        cursor.execute(
            """
            DELETE FROM projects
            WHERE project_id = %s
            AND user_id = %s
            """,
            (
                project_id,
                session["user_id"]
            )
        )

        conn.commit()

        return {
            "message": "Project deleted successfully."
        }, 200

    except mysql.connector.Error as error:
        if conn:
            conn.rollback()

        return {
            "message": "Unable to delete project."
        }, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

# =========================
# TASK APIs
# =========================

@app.route("/api/tasks", methods=["GET"])
def get_tasks():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                t.task_id,
                t.title,
                t.description,
                t.priority,
                t.due_date,
                t.due_time,
                t.is_completed,
                t.is_important,
                t.is_starred,
                t.project_id,
                t.created_at
            FROM tasks t
            WHERE t.user_id = %s
            ORDER BY t.created_at DESC
            """,
            (session["user_id"],)
        )

        tasks = cursor.fetchall()

        for task in tasks:

            if task["due_date"]:
                task["due_date"] = str(task["due_date"])

            if task["due_time"]:
                task["due_time"] = str(task["due_time"])

            task["is_completed"] = bool(task["is_completed"])
            task["is_important"] = bool(task["is_important"])
            task["is_starred"] = bool(task["is_starred"])

            cursor.execute(
                """
                SELECT tg.tag_name
                FROM tags tg
                JOIN task_tags tt ON tg.tag_id = tt.tag_id
                WHERE tt.task_id = %s
                AND tg.user_id = %s
                ORDER BY tg.tag_name
                """,
                (task["task_id"], session["user_id"])
            )

            tag_rows = cursor.fetchall()
            task["tags"] = [row["tag_name"] for row in tag_rows]
    
            # Load subtasks
            cursor.execute(
                """
                SELECT subtask_id, title, is_completed
                FROM subtasks
                WHERE task_id = %s
                ORDER BY subtask_id
                """,
                (task["task_id"],)
            )

            subtask_rows = cursor.fetchall()

            task["subtasks"] = [
                {
                    "id": str(row["subtask_id"]),
                    "title": row["title"],
                    "done": bool(row["is_completed"])
                }
                for row in subtask_rows
            ]
        return {"tasks": tasks}, 200

    except mysql.connector.Error:
        return {"message": "Unable to load tasks."}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks", methods=["POST"])
def create_task():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}

    title = data.get("title")
    description = data.get("description")
    priority = data.get("priority", "medium")
    due_date = data.get("due_date")
    due_time = data.get("due_time")
    project_id = data.get("project_id")
    tags = data.get("tags", [])
    subtasks = data.get("subtasks", [])

    if not isinstance(title, str) or not title.strip():
        return {"message": "Task title is required."}, 400

    title = title.strip()

    if priority not in ["low", "medium", "high", "urgent"]:
        priority = "medium"

    # Security: verify project belongs to logged-in user
    if project_id is not None:

        check_conn = None
        check_cursor = None

        try:
            check_conn = get_db_connection()
            check_cursor = check_conn.cursor()

            check_cursor.execute(
                """
                SELECT project_id
                FROM projects
                WHERE project_id = %s
                AND user_id = %s
                """,
                (
                    project_id,
                    session["user_id"]
                )
            )

            if not check_cursor.fetchone():
                return {"message": "Invalid project."}, 403

        finally:

            if check_cursor:
                check_cursor.close()

            if check_conn:
                check_conn.close()
        if not isinstance(subtasks, list):
          return {"message": "Invalid subtasks."}, 400

    clean_subtasks = []

    for subtask in subtasks:
        if not isinstance(subtask, dict):
            continue

        subtask_title = subtask.get("title")

        if not isinstance(subtask_title, str):
            continue

        subtask_title = subtask_title.strip()

        if subtask_title:
            if len(subtask_title) > 255:
                return {"message": "Subtask title is too long."}, 400

            clean_subtasks.append(subtask_title)

    if len(clean_subtasks) > 100:
        return {"message": "Too many subtasks."}, 400
    # Validate tags
    if not isinstance(tags, list):
        return {"message": "Invalid tags."}, 400

    clean_tags = []

    for tag in tags:

        if not isinstance(tag, str):
            continue

        tag = tag.strip().lower().replace("#", "")

        if not tag:
            continue

        if len(tag) > 50:
            return {"message": "Tag is too long."}, 400

        if tag not in clean_tags:
            clean_tags.append(tag)

    conn = None
    cursor = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor()

        # Create task
        cursor.execute(
            """
            INSERT INTO tasks
            (
                user_id,
                project_id,
                title,
                description,
                priority,
                due_date,
                due_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session["user_id"],
                project_id,
                title,
                description,
                priority,
                due_date,
                due_time
            )
        )

        task_id = cursor.lastrowid
        
        # Save subtasks
        for subtask_title in clean_subtasks:
            cursor.execute(
                """
                INSERT INTO subtasks (task_id, title)
                VALUES (%s, %s)
                """,
                (task_id, subtask_title)
            )
        # Save tags
        for tag in clean_tags:

            cursor.execute(
                """
                SELECT tag_id
                FROM tags
                WHERE user_id = %s
                AND tag_name = %s
                """,
                (
                    session["user_id"],
                    tag
                )
            )

            existing_tag = cursor.fetchone()

            if existing_tag:

                tag_id = existing_tag[0]

            else:

                cursor.execute(
                    """
                    INSERT INTO tags
                    (
                        user_id,
                        tag_name
                    )
                    VALUES (%s, %s)
                    """,
                    (
                        session["user_id"],
                        tag
                    )
                )

                tag_id = cursor.lastrowid

            # Connect tag with task
            cursor.execute(
                """
                INSERT INTO task_tags
                (
                    task_id,
                    tag_id
                )
                VALUES (%s, %s)
                """,
                (
                    task_id,
                    tag_id
                )
            )

        conn.commit()

        return {
            "message": "Task created successfully.",
            "task_id": task_id
        }, 201

    except mysql.connector.Error:

        if conn:
            conn.rollback()

        return {
            "message": "Unable to create task."
        }, 500

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


@app.route("/api/tasks/<int:task_id>/subtasks/<int:subtask_id>", methods=["PATCH"])
def update_subtask_status(task_id, subtask_id):
    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}
    completed = data.get("is_completed")

    if not isinstance(completed, bool):
        return {"message": "Invalid completion status."}, 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE subtasks
            JOIN tasks ON tasks.task_id = subtasks.task_id
            SET subtasks.is_completed = %s
            WHERE subtasks.subtask_id = %s
              AND subtasks.task_id = %s
              AND tasks.user_id = %s
            """,
            (completed, subtask_id, task_id, session["user_id"])
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return {"message": "Subtask not found."}, 404

        conn.commit()
        return {"message": "Subtask status saved."}, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()
        return {"message": "Unable to save subtask status."}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}

    title = data.get("title")
    description = data.get("description")
    project_id = data.get("project_id")
    priority = data.get("priority", "medium")
    due_date = data.get("due_date")
    due_time = data.get("due_time")
    tags = data.get("tags", [])
    subtasks = data.get("subtasks", [])

    if not isinstance(title, str) or not title.strip():
        return {"message": "Task title is required."}, 400

    title = title.strip()

    if len(title) > 255:
        return {"message": "Task title is too long."}, 400

    if priority not in ["low", "medium", "high", "urgent"]:
        priority = "medium"

    if project_id == "":
        project_id = None

    if project_id is not None:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return {"message": "Invalid project."}, 400

    if not isinstance(tags, list):
        return {"message": "Invalid tags."}, 400

    clean_tags = []

    for tag in tags:
        if not isinstance(tag, str):
            continue

        tag = tag.strip().lower().replace("#", "")

        if not tag:
            continue

        if len(tag) > 50:
            return {"message": "Tag is too long."}, 400

        if tag not in clean_tags:
            clean_tags.append(tag)

    if not isinstance(subtasks, list):
        return {"message": "Invalid subtasks."}, 400

    if len(subtasks) > 100:
        return {"message": "Too many subtasks."}, 400

    clean_subtasks = []

    for subtask in subtasks:
        if not isinstance(subtask, dict):
            continue

        subtask_title = subtask.get("title")

        if not isinstance(subtask_title, str):
            continue

        subtask_title = subtask_title.strip()

        if not subtask_title:
            continue

        if len(subtask_title) > 255:
            return {"message": "Subtask title is too long."}, 400

        clean_subtasks.append({
            "title": subtask_title,
            "is_completed": bool(subtask.get("is_completed", False))
        })

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify project ownership
        if project_id is not None:
            cursor.execute(
                """
                SELECT project_id
                FROM projects
                WHERE project_id = %s AND user_id = %s
                """,
                (project_id, session["user_id"])
            )

            if not cursor.fetchone():
                return {"message": "Invalid project."}, 403

        # Verify task ownership
        cursor.execute(
            """
            SELECT task_id
            FROM tasks
            WHERE task_id = %s AND user_id = %s
            """,
            (task_id, session["user_id"])
        )

        if not cursor.fetchone():
            return {"message": "Task not found."}, 404

        # Update task
        cursor.execute(
            """
            UPDATE tasks
            SET title = %s,
                description = %s,
                project_id = %s,
                priority = %s,
                due_date = %s,
                due_time = %s
            WHERE task_id = %s AND user_id = %s
            """,
            (
                title,
                description,
                project_id,
                priority,
                due_date,
                due_time,
                task_id,
                session["user_id"]
            )
        )

        # Replace old tag connections
        cursor.execute(
            "DELETE FROM task_tags WHERE task_id = %s",
            (task_id,)
        )

        for tag in clean_tags:
            cursor.execute(
                """
                SELECT tag_id FROM tags
                WHERE user_id = %s AND tag_name = %s
                """,
                (session["user_id"], tag)
            )

            existing_tag = cursor.fetchone()

            if existing_tag:
                tag_id = existing_tag[0]
            else:
                cursor.execute(
                    """
                    INSERT INTO tags (user_id, tag_name)
                    VALUES (%s, %s)
                    """,
                    (session["user_id"], tag)
                )
                tag_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO task_tags (task_id, tag_id)
                VALUES (%s, %s)
                """,
                (task_id, tag_id)
            )

        # Replace old subtasks
        cursor.execute(
            "DELETE FROM subtasks WHERE task_id = %s",
            (task_id,)
        )

        # Save updated subtasks
        for subtask in clean_subtasks:
            cursor.execute(
                """
                INSERT INTO subtasks
                    (task_id, title, is_completed)
                VALUES (%s, %s, %s)
                """,
                (
                    task_id,
                    subtask["title"],
                    subtask["is_completed"]
                )
            )

        conn.commit()

        return {"message": "Task updated successfully."}, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()

        return {"message": "Unable to update task."}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks/<int:task_id>/star", methods=["PUT"])
def star_task(task_id):

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}
    is_starred = bool(data.get("is_starred", False))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tasks
            SET is_starred = %s
            WHERE task_id = %s AND user_id = %s
            """,
            (
                is_starred,
                task_id,
                session["user_id"]
            )
        )

        conn.commit()

        if cursor.rowcount == 0:
            return {"message": "Task not found."}, 404

        return {
            "message": "Star status updated successfully."
        }, 200

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):



    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM tasks
            WHERE task_id = %s AND user_id = %s
            """,
            (
                task_id,
                session["user_id"]
            )
        )

        conn.commit()

        if cursor.rowcount == 0:
            return {"message": "Task not found."}, 404

        return {
            "message": "Task deleted successfully."
        }, 200

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks/bulk-delete", methods=["DELETE"])
def bulk_delete_tasks():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}
    task_ids = data.get("task_ids", [])

    if not isinstance(task_ids, list) or not task_ids:
        return {"message": "No tasks selected."}, 400

    # Security: validate every task ID
    try:
        task_ids = [int(task_id) for task_id in task_ids]
    except (TypeError, ValueError):
        return {"message": "Invalid task IDs."}, 400

    if any(task_id <= 0 for task_id in task_ids):
        return {"message": "Invalid task IDs."}, 400

    # Remove duplicate IDs
    task_ids = list(set(task_ids))

    conn = None
    cursor = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor()

        placeholders = ",".join(["%s"] * len(task_ids))

        query = f"""
            DELETE FROM tasks
            WHERE task_id IN ({placeholders})
            AND user_id = %s
        """

        cursor.execute(
            query,
            tuple(task_ids) + (session["user_id"],)
        )

        conn.commit()

        return {
            "message": "Selected tasks deleted successfully.",
            "deleted_count": cursor.rowcount
        }, 200

    except mysql.connector.Error:

        if conn:
            conn.rollback()

        return {
            "message": "Unable to delete selected tasks."
        }, 500

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks/clear-completed", methods=["DELETE"])
def clear_completed_tasks():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    conn = None
    cursor = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM tasks
            WHERE user_id = %s
            AND is_completed = %s
            """,
            (
                session["user_id"],
                True
            )
        )

        deleted_count = cursor.rowcount

        conn.commit()

        return {
            "message": "Completed tasks cleared successfully.",
            "deleted_count": deleted_count
        }, 200

    except mysql.connector.Error:

        if conn:
            conn.rollback()

        return {
            "message": "Unable to clear completed tasks."
        }, 500

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks/bulk-complete", methods=["PUT"])
def bulk_complete_tasks():

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}
    task_ids = data.get("task_ids", [])

    if not isinstance(task_ids, list) or not task_ids:
        return {"message": "No tasks selected."}, 400

    # Security: only valid integer IDs
    try:
        task_ids = [int(task_id) for task_id in task_ids]
    except (TypeError, ValueError):
        return {"message": "Invalid task IDs."}, 400

    if any(task_id <= 0 for task_id in task_ids):
        return {"message": "Invalid task IDs."}, 400

    conn = None
    cursor = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor()

        placeholders = ",".join(["%s"] * len(task_ids))

        query = f"""
            UPDATE tasks
            SET is_completed = %s
            WHERE task_id IN ({placeholders})
            AND user_id = %s
        """

        cursor.execute(
            query,
            tuple([True] + task_ids + [session["user_id"]])
        )

        conn.commit()

        return {
            "message": "Selected tasks completed successfully.",
            "completed_count": cursor.rowcount
        }, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()

        return {
            "message": "Unable to complete selected tasks."
        }, 500

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

@app.route("/api/tasks/<int:task_id>/complete", methods=["PUT"])
def complete_task(task_id):

    if "user_id" not in session:
        return {"message": "Please login first."}, 401

    data = request.get_json() or {}
    is_completed = bool(data.get("is_completed", False))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE tasks
            SET is_completed = %s
            WHERE task_id = %s AND user_id = %s
            """,
            (
                is_completed,
                task_id,
                session["user_id"]
            )
        )

        conn.commit()

        if cursor.rowcount == 0:
            return {"message": "Task not found."}, 404

        return {
            "message": "Task status updated successfully."
        }, 200

    except mysql.connector.Error as error:
        return {"message": f"Database error: {error}"}, 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(debug=True)