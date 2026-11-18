# Quiz Management System (Python + MySQL)

A console-based quiz application with separate Admin and Student portals.

## Features

### Admin
- Login with a seeded administrator account
- Create quizzes
- Activate/deactivate quizzes
- Add, view, modify and delete multiple-choice questions
- Register student accounts
- View all submitted results

### Student
- Register and log in
- View active quizzes
- Attempt multiple-choice quizzes
- Skip questions
- Receive automatic scores and percentages
- View previous results

## Requirements
- Python 3.10+
- MySQL Server running locally
- MySQL account allowed to create a database

## Setup (Windows PowerShell)

1. Extract the project ZIP and open its folder in VS Code.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Edit `.env`. Set your local MySQL password in `DB_PASSWORD`.
   Set a strong first-run `ADMIN_PASSWORD` of at least 12 characters.
   Do not share or commit `.env` to GitHub.

6. Run:

   ```powershell
   python app.py
   ```

The app creates the `quiz_management` database and required tables automatically.
It creates the first admin only if `ADMIN_USERNAME` does not already exist.

Default admin username is `admin`; choose your own password in `.env` before
the first run. If you change the admin password in `.env` after the account
has already been created, it will not automatically overwrite the database
password. Change it through a future password-management feature or update
the account deliberately.

## Database design

- `users`: admin and student accounts
- `quizzes`: quiz metadata and active status
- `questions`: question text, four options, correct option and marks
- `attempts`: one submitted attempt and its score
- `attempt_answers`: each selected answer and awarded marks

## Important notes

- The project uses parameterized SQL queries.
- Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, not plaintext.
- The quiz answer key is not displayed to students.
- Quiz attempts are committed in a database transaction.
- This is a learning/demo console application. Before production deployment,
  add password reset, audit logging, rate limiting, authorization tests,
  stronger operational secrets management and a web interface.
