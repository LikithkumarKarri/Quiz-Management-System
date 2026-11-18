import os
import hashlib
import hmac
import secrets
import getpass
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "quiz_management"),
}

def connect():
    return mysql.connector.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    """PBKDF2 password hash; the random salt is stored with the hash."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 200_000
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

def setup_database():
    """Create tables and seed the first admin account."""
    # Create the database first, because the configured database may not exist yet.
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"], user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    cur = conn.cursor()
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.close()
    conn.close()

    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(60) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role ENUM('admin','student') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            quiz_id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            question_id INT AUTO_INCREMENT PRIMARY KEY,
            quiz_id INT NOT NULL,
            question_text TEXT NOT NULL,
            option_a VARCHAR(500) NOT NULL,
            option_b VARCHAR(500) NOT NULL,
            option_c VARCHAR(500) NOT NULL,
            option_d VARCHAR(500) NOT NULL,
            correct_option ENUM('A','B','C','D') NOT NULL,
            marks INT NOT NULL DEFAULT 1,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id INT AUTO_INCREMENT PRIMARY KEY,
            quiz_id INT NOT NULL,
            student_id INT NOT NULL,
            score INT NOT NULL DEFAULT 0,
            total_marks INT NOT NULL DEFAULT 0,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempt_answers (
            answer_id INT AUTO_INCREMENT PRIMARY KEY,
            attempt_id INT NOT NULL,
            question_id INT NOT NULL,
            selected_option ENUM('A','B','C','D') NULL,
            is_correct BOOLEAN NOT NULL DEFAULT FALSE,
            marks_awarded INT NOT NULL DEFAULT 0,
            FOREIGN KEY (attempt_id) REFERENCES attempts(attempt_id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
            UNIQUE KEY uq_attempt_question (attempt_id, question_id)
        )
    """)
    admin_name = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_password and len(admin_password) >= 12:
        cur.execute("SELECT user_id FROM users WHERE username=%s", (admin_name,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO users(username,password_hash,role) VALUES(%s,%s,'admin')",
                (admin_name, hash_password(admin_password))
            )
    conn.commit()
    cur.close()
    conn.close()

def fetch_all(sql, params=()):
    conn = connect()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def execute(sql, params=()):
    conn = connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    cur.close()
    conn.close()
    return last_id

def ask_int(prompt, minimum=1):
    while True:
        try:
            value = int(input(prompt))
            if value >= minimum:
                return value
            print(f"Enter a number greater than or equal to {minimum}.")
        except ValueError:
            print("Please enter a valid whole number.")

def login(role):
    print(f"\n--- {role.upper()} LOGIN ---")
    for attempt in range(3):
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        rows = fetch_all(
            "SELECT user_id,username,password_hash,role FROM users WHERE username=%s",
            (username,)
        )
        if rows and rows[0]["role"] == role and verify_password(password, rows[0]["password_hash"]):
            print(f"\nWelcome, {username}!")
            return rows[0]
        print(f"Invalid credentials. Attempts remaining: {2-attempt}")
    return None

def register_student():
    print("\n--- STUDENT REGISTRATION ---")
    username = input("Choose username: ").strip()
    if len(username) < 3:
        print("Username must contain at least 3 characters.")
        return
    password = getpass.getpass("Choose password (minimum 8 characters): ")
    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return
    try:
        execute(
            "INSERT INTO users(username,password_hash,role) VALUES(%s,%s,'student')",
            (username, hash_password(password))
        )
        print("Student registered successfully.")
    except mysql.connector.IntegrityError:
        print("That username is already taken.")

def list_quizzes(active_only=False):
    sql = """
        SELECT q.quiz_id,q.title,q.description,q.is_active,
               COUNT(ques.question_id) AS question_count
        FROM quizzes q LEFT JOIN questions ques ON q.quiz_id=ques.quiz_id
    """
    if active_only:
        sql += " WHERE q.is_active=TRUE"
    sql += " GROUP BY q.quiz_id ORDER BY q.quiz_id"
    rows = fetch_all(sql)
    if not rows:
        print("No quizzes found.")
        return []
    print("\nID | Quiz title | Questions | Status")
    print("-" * 65)
    for q in rows:
        print(f"{q['quiz_id']} | {q['title']} | {q['question_count']} | "
              f"{'Active' if q['is_active'] else 'Inactive'}")
    return rows

def add_quiz(admin):
    print("\n--- ADD QUIZ ---")
    title = input("Quiz title: ").strip()
    if not title:
        print("Title cannot be empty.")
        return
    description = input("Description: ").strip()
    execute(
        "INSERT INTO quizzes(title,description,created_by) VALUES(%s,%s,%s)",
        (title, description, admin["user_id"])
    )
    print("Quiz created.")

def toggle_quiz():
    list_quizzes()
    quiz_id = ask_int("Quiz ID to activate/deactivate: ")
    rows = fetch_all("SELECT is_active FROM quizzes WHERE quiz_id=%s", (quiz_id,))
    if not rows:
        print("Quiz not found.")
        return
    execute("UPDATE quizzes SET is_active=%s WHERE quiz_id=%s",
            (not rows[0]["is_active"], quiz_id))
    print("Quiz status updated.")

def add_question():
    list_quizzes()
    quiz_id = ask_int("Quiz ID: ")
    if not fetch_all("SELECT quiz_id FROM quizzes WHERE quiz_id=%s", (quiz_id,)):
        print("Quiz not found.")
        return
    question = input("Question: ").strip()
    options = [input(f"Option {letter}: ").strip() for letter in "ABCD"]
    correct = input("Correct option (A/B/C/D): ").strip().upper()
    if not question or any(not x for x in options) or correct not in "ABCD" or len(correct) != 1:
        print("Question/options must not be empty; correct option must be A, B, C or D.")
        return
    marks = ask_int("Marks for this question: ")
    execute("""
        INSERT INTO questions
        (quiz_id,question_text,option_a,option_b,option_c,option_d,correct_option,marks)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
    """, (quiz_id, question, *options, correct, marks))
    print("Question added.")

def view_questions():
    list_quizzes()
    quiz_id = ask_int("Quiz ID to view: ")
    rows = fetch_all("""
        SELECT question_id,question_text,option_a,option_b,option_c,option_d,marks
        FROM questions WHERE quiz_id=%s ORDER BY question_id
    """, (quiz_id,))
    if not rows:
        print("No questions found.")
        return
    for q in rows:
        print(f"\nQ{q['question_id']}. {q['question_text']} ({q['marks']} mark(s))")
        for letter in "ABCD":
            print(f"  {letter}. {q['option_' + letter.lower()]}")

def modify_question():
    view_questions()
    qid = ask_int("\nQuestion ID to modify: ")
    rows = fetch_all("SELECT * FROM questions WHERE question_id=%s", (qid,))
    if not rows:
        print("Question not found.")
        return
    q = rows[0]
    question = input(f"Question [{q['question_text']}]: ").strip() or q["question_text"]
    values = []
    for letter in "ABCD":
        old = q["option_" + letter.lower()]
        values.append(input(f"Option {letter} [{old}]: ").strip() or old)
    correct = input(f"Correct option [{q['correct_option']}]: ").strip().upper() or q["correct_option"]
    if correct not in ("A", "B", "C", "D"):
        print("Invalid correct option.")
        return
    marks_text = input(f"Marks [{q['marks']}]: ").strip()
    marks = int(marks_text) if marks_text else q["marks"]
    if marks < 1:
        print("Marks must be positive.")
        return
    execute("""
        UPDATE questions SET question_text=%s,option_a=%s,option_b=%s,
        option_c=%s,option_d=%s,correct_option=%s,marks=%s WHERE question_id=%s
    """, (question, *values, correct, marks, qid))
    print("Question updated.")

def delete_question():
    view_questions()
    qid = ask_int("\nQuestion ID to delete: ")
    if input(f"Confirm deletion of question {qid}? (y/n): ").strip().lower() == "y":
        execute("DELETE FROM questions WHERE question_id=%s", (qid,))
        print("Question deleted if it existed.")
    else:
        print("Cancelled.")

def admin_results():
    rows = fetch_all("""
        SELECT a.attempt_id,u.username,q.title,a.score,a.total_marks,a.submitted_at
        FROM attempts a JOIN users u ON a.student_id=u.user_id
        JOIN quizzes q ON a.quiz_id=q.quiz_id
        ORDER BY a.submitted_at DESC
    """)
    if not rows:
        print("No submitted attempts yet.")
        return
    print("\nAttempt | Student | Quiz | Score | Submitted")
    for r in rows:
        print(f"{r['attempt_id']} | {r['username']} | {r['title']} | "
              f"{r['score']}/{r['total_marks']} | {r['submitted_at']}")

def admin_menu(admin):
    while True:
        print("""
========== ADMIN MENU ==========
1. Add quiz
2. View quizzes
3. Activate/deactivate quiz
4. Add question
5. View questions
6. Modify question
7. Delete question
8. Register student
9. View all results
0. Logout
""")
        choice = input("Choose: ").strip()
        actions = {
            "1": lambda: add_quiz(admin), "2": lambda: list_quizzes(),
            "3": toggle_quiz, "4": add_question, "5": view_questions,
            "6": modify_question, "7": delete_question,
            "8": register_student, "9": admin_results
        }
        if choice == "0":
            return
        action = actions.get(choice)
        if action:
            try:
                action()
            except (ValueError, Error) as exc:
                print(f"Operation failed: {exc}")
        else:
            print("Invalid selection.")

def student_quiz(student):
    list_quizzes(active_only=True)
    quiz_id = ask_int("Enter quiz ID to start: ")
    quiz = fetch_all("SELECT title FROM quizzes WHERE quiz_id=%s AND is_active=TRUE", (quiz_id,))
    questions = fetch_all("""
        SELECT question_id,question_text,option_a,option_b,option_c,option_d,
               correct_option,marks
        FROM questions WHERE quiz_id=%s ORDER BY question_id
    """, (quiz_id,))
    if not quiz:
        print("Active quiz not found.")
        return
    if not questions:
        print("This quiz has no questions yet.")
        return

    answers = {}
    print(f"\n========== {quiz[0]['title']} ==========")
    for number, q in enumerate(questions, 1):
        print(f"\n{number}. {q['question_text']} ({q['marks']} mark(s))")
        for letter in "ABCD":
            print(f"  {letter}. {q['option_' + letter.lower()]}")
        answer = input("Your answer (A/B/C/D, or Enter to skip): ").strip().upper()
        answers[q["question_id"]] = answer if answer in ("A", "B", "C", "D") else None

    score = 0
    total = sum(q["marks"] for q in questions)
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO attempts(quiz_id,student_id,score,total_marks) VALUES(%s,%s,0,%s)",
            (quiz_id, student["user_id"], total)
        )
        attempt_id = cur.lastrowid
        for q in questions:
            selected = answers[q["question_id"]]
            correct = selected == q["correct_option"]
            awarded = q["marks"] if correct else 0
            score += awarded
            cur.execute("""
                INSERT INTO attempt_answers
                (attempt_id,question_id,selected_option,is_correct,marks_awarded)
                VALUES(%s,%s,%s,%s,%s)
            """, (attempt_id, q["question_id"], selected, correct, awarded))
        cur.execute("UPDATE attempts SET score=%s WHERE attempt_id=%s", (score, attempt_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print("\n========== RESULT ==========")
    print(f"Quiz: {quiz[0]['title']}")
    print(f"Your score: {score}/{total}")
    print(f"Percentage: {(score/total)*100:.2f}%")

def student_results(student):
    rows = fetch_all("""
        SELECT q.title,a.score,a.total_marks,a.submitted_at
        FROM attempts a JOIN quizzes q ON a.quiz_id=q.quiz_id
        WHERE a.student_id=%s ORDER BY a.submitted_at DESC
    """, (student["user_id"],))
    if not rows:
        print("You have not attempted any quizzes.")
        return
    for r in rows:
        print(f"{r['title']} | {r['score']}/{r['total_marks']} | {r['submitted_at']}")

def student_menu(student):
    while True:
        print("""
========== STUDENT MENU ==========
1. View available quizzes
2. Start quiz
3. View my scores
0. Logout
""")
        choice = input("Choose: ").strip()
        try:
            if choice == "1":
                list_quizzes(active_only=True)
            elif choice == "2":
                student_quiz(student)
            elif choice == "3":
                student_results(student)
            elif choice == "0":
                return
            else:
                print("Invalid selection.")
        except (ValueError, Error) as exc:
            print(f"Operation failed: {exc}")

def main():
    print("=" * 58)
    print("                 QUIZ MANAGEMENT SYSTEM")
    print("=" * 58)
    try:
        setup_database()
        while True:
            print("\n1. Admin login\n2. Student login\n3. Student registration\n0. Exit")
            choice = input("Select: ").strip()
            if choice == "1":
                user = login("admin")
                if user:
                    admin_menu(user)
            elif choice == "2":
                user = login("student")
                if user:
                    student_menu(user)
            elif choice == "3":
                register_student()
            elif choice == "0":
                print("Thank you. Goodbye!")
                break
            else:
                print("Invalid selection.")
    except Error as exc:
        print("\nDatabase connection/setup failed.")
        print("Check that MySQL Server is running and your .env settings are correct.")
        print(f"Details: {exc}")

if __name__ == "__main__":
    main()
