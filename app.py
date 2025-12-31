import json

import pymysql
from flask import Flask, render_template, request, redirect, url_for, session

from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config["SECRET_KEY"]


def get_db_connection():
    return pymysql.connect(
        host=app.config["DB_HOST"],
        port=app.config["DB_PORT"],
        user=app.config["DB_USER"],
        password=app.config["DB_PASSWORD"],
        db=app.config["DB_NAME"],
        cursorclass=pymysql.cursors.DictCursor,
    )


from datetime import date, timedelta
import json
from flask import render_template, session

@app.route("/", methods=["GET"])
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
          SUM(
            CASE
              WHEN direction = 0 AND (principal - paid) > 0 THEN (principal - paid)
              ELSE 0
            END
          ) AS i_owe
        FROM loans
        """
    )
    i_owe = cur.fetchone()["i_owe"] or 0

    cur.execute(
        """
        SELECT
          SUM(
            CASE
              WHEN direction = 1 AND (principal - paid) > 0 THEN (principal - paid)
              ELSE 0
            END
          ) AS owed_to_me
        FROM loans
        """
    )
    owed_to_me = cur.fetchone()["owed_to_me"] or 0

    net_position = owed_to_me - i_owe

    cur.execute(
        """
        SELECT COUNT(*) AS overdue
        FROM loans
        WHERE (principal - paid) > 0
          AND due_date < CURDATE()
        """
    )
    overdue_loans = cur.fetchone()["overdue"] or 0

    cur.execute(
        """
        SELECT
          l.id AS loan_id,
          p.name,
          (l.principal - l.paid) AS amount,
          DATEDIFF(CURDATE(), l.due_date) AS days
        FROM loans l
        JOIN people p ON l.person_id = p.id
        WHERE (l.principal - l.paid) > 0
          AND l.due_date < CURDATE()
        ORDER BY days DESC
        LIMIT 5
        """
    )
    overdue_list = cur.fetchall()

    window_days = 31
    today = date.today()
    end = today + timedelta(days=window_days)

    cur.execute(
        """
        SELECT
          l.id AS loan_id,
          p.id AS person_id,
          p.name AS person_name,
          l.due_date,
          (l.principal - l.paid) AS remaining,
          l.notes
        FROM loans l
        JOIN people p ON l.person_id = p.id
        WHERE (l.principal - l.paid) > 0
          AND l.due_date >= %s
          AND l.due_date <= %s
          AND l.direction = 0
        ORDER BY l.due_date ASC, l.id ASC
        """,
        (today, end),
    )
    upcoming_i_owe = cur.fetchall()
    upcoming_i_owe_total = sum(float(r["remaining"] or 0) for r in upcoming_i_owe)

    cur.execute(
        """
        SELECT
          l.id AS loan_id,
          p.id AS person_id,
          p.name AS person_name,
          l.due_date,
          (l.principal - l.paid) AS remaining,
          l.notes
        FROM loans l
        JOIN people p ON l.person_id = p.id
        WHERE (l.principal - l.paid) > 0
          AND l.due_date >= %s
          AND l.due_date <= %s
          AND l.direction = 1
        ORDER BY l.due_date ASC, l.id ASC
        """,
        (today, end),
    )
    upcoming_owed_to_me = cur.fetchall()
    upcoming_owed_to_me_total = sum(float(r["remaining"] or 0) for r in upcoming_owed_to_me)

    monthly_cashflow = {
        "labels": ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "data": [50000, 80000, 50000, 70000, 60000, 40000],
        "colors": ["#111827", "#9CA3AF", "#9CA3AF", "#111827", "#9CA3AF", "#111827"],
    }

    cur.execute(
        """
        SELECT p.name, SUM(l.principal - l.paid) AS amount
        FROM loans l
        JOIN people p ON l.person_id = p.id
        WHERE (l.principal - l.paid) > 0
        GROUP BY p.id
        """
    )
    outstanding_pie_rows = cur.fetchall()

    cur.close()
    conn.close()

    outstanding_pie = [
        {"name": row["name"], "amount": float(row["amount"] or 0)}
        for row in outstanding_pie_rows
    ]

    theme = session.get("theme", app.config["DEFAULT_THEME"])

    return render_template(
        "dashboard.html",
        i_owe=i_owe,
        owed_to_me=owed_to_me,
        net_position=net_position,
        overdue_loans=overdue_loans,
        overdue_list=overdue_list,
        upcoming_i_owe=upcoming_i_owe,
        upcoming_i_owe_total=upcoming_i_owe_total,
        upcoming_owed_to_me=upcoming_owed_to_me,
        upcoming_owed_to_me_total=upcoming_owed_to_me_total,
        monthly_cashflow=json.dumps(monthly_cashflow),
        outstanding_pie=json.dumps(outstanding_pie),
        theme=theme,
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        theme = request.form.get("theme", "light")
        session["theme"] = "dark" if theme == "dark" else "light"
        return redirect(url_for("settings"))

    theme = session.get("theme", app.config["DEFAULT_THEME"])
    currency = "PKR"
    due_reminders = False
    overdue_alerts = False

    return render_template(
        "settings.html",
        theme=theme,
        currency=currency,
        due_reminders=due_reminders,
        overdue_alerts=overdue_alerts,
    )


@app.route("/people", methods=["GET"])
def people():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.*,
               (
                   SELECT COUNT(*)
                   FROM loans l
                   WHERE l.person_id = p.id
                     AND principal > paid
               ) AS active_loans,
               (
                   SELECT SUM(
                       CASE WHEN direction = 0
                            THEN principal - paid
                            ELSE 0
                       END
                   )
                   FROM loans l
                   WHERE l.person_id = p.id
               ) AS i_owe,
               (
                   SELECT SUM(
                       CASE WHEN direction = 1
                            THEN principal - paid
                            ELSE 0
                       END
                   )
                   FROM loans l
                   WHERE l.person_id = p.id
               ) AS they_owe
        FROM people p
        """
    )
    people_list = cur.fetchall()
    cur.close()
    conn.close()

    theme = session.get("theme", app.config["DEFAULT_THEME"])
    return render_template("people.html", people=people_list, theme=theme)


@app.route("/add_person", methods=["POST"])
def add_person():
    conn = get_db_connection()
    cur = conn.cursor()

    name = request.form["name"]
    phone = request.form["phone"]
    email = request.form.get("email", "")
    notes = request.form.get("notes", "")

    cur.execute(
        "INSERT INTO people (name, phone, email, notes) "
        "VALUES (%s, %s, %s, %s)",
        (name, phone, email, notes),
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("people"))


@app.route("/loans", methods=["GET"])
def loans():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT l.*,
               p.name,
               CASE
                   WHEN principal <= paid THEN 'Closed'
                   WHEN due_date < CURDATE() THEN 'Overdue'
                   ELSE 'Active'
               END AS status
        FROM loans l
        JOIN people p ON l.person_id = p.id
        """
    )
    loans_list = cur.fetchall()

    cur.execute("SELECT id, name FROM people")
    people_list = cur.fetchall()

    cur.close()
    conn.close()

    theme = session.get("theme", app.config["DEFAULT_THEME"])

    return render_template(
        "loans.html",
        loans=loans_list,
        people=people_list,
        theme=theme,
    )


@app.route("/add_loan", methods=["POST"])
def add_loan():
    conn = get_db_connection()
    cur = conn.cursor()

    person_id = request.form["person"]
    direction = int(request.form["direction"])
    principal = float(request.form["principal"])
    due_date = request.form["due_date"]
    given_date = request.form["given_date"]
    notes = request.form.get("notes", "")
    paid = 0.0

    cur.execute(
        """
        INSERT INTO loans (person_id, direction, principal, paid, given_date, due_date, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (person_id, direction, principal, paid, given_date, due_date, notes),
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("loans"))


@app.route("/reports", methods=["GET"])
def reports():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT SUM(principal) AS total_principal FROM loans")
    total_principal = cur.fetchone()["total_principal"] or 0

    cur.execute("SELECT COUNT(*) AS active FROM loans WHERE principal > paid")
    active_loans = cur.fetchone()["active"]

    cur.execute("SELECT COUNT(*) AS closed FROM loans WHERE principal <= paid")
    closed_loans = cur.fetchone()["closed"]

    cur.execute("SELECT COUNT(DISTINCT person_id) AS total_people FROM loans")
    total_people = cur.fetchone()["total_people"] or 0

    monthly_line = {
        "labels": ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "data": [90000, 80000, 60000, 50000, 40000, 20000],
    }

    cur.execute(
        """
        SELECT p.name,
               SUM(
                   CASE WHEN direction = 0
                        THEN principal - paid
                        ELSE 0
               END
               ) AS i_owe,
               SUM(
                   CASE WHEN direction = 1
                        THEN principal - paid
                        ELSE 0
               END
               ) AS owed_to_me
        FROM loans l
        JOIN people p ON l.person_id = p.id
        WHERE principal > paid
        GROUP BY p.id
        """
    )
    balance_bar_rows = cur.fetchall()

    cur.execute(
        """
        SELECT SUM(
            CASE WHEN direction = 0
                 THEN principal - paid
                 ELSE 0
            END
        ) AS i_owe
        FROM loans
        WHERE principal > paid
        """
    )
    pie_i_owe = cur.fetchone()["i_owe"] or 0

    cur.execute(
        """
        SELECT SUM(
            CASE WHEN direction = 1
                 THEN principal - paid
                 ELSE 0
            END
        ) AS owed_to_me
        FROM loans
        WHERE principal > paid
        """
    )
    pie_owed = cur.fetchone()["owed_to_me"] or 0

    cur.close()
    conn.close()

    balance_bar = [
        {
            "name": row["name"],
            "i_owe": float(row["i_owe"] or 0),
            "owed_to_me": float(row["owed_to_me"] or 0),
        }
        for row in balance_bar_rows
    ]

    outstanding_direction = {
        "i_owe": float(pie_i_owe or 0),
        "owed_to_me": float(pie_owed or 0),
    }
    status_pie = {"active": active_loans, "closed": closed_loans}

    theme = session.get("theme", app.config["DEFAULT_THEME"])

    return render_template(
        "reports.html",
        total_principal=total_principal,
        active_loans=active_loans,
        closed_loans=closed_loans,
        total_people=total_people,
        monthly_line=json.dumps(monthly_line),
        balance_bar=json.dumps(balance_bar),
        outstanding_direction=json.dumps(outstanding_direction),
        status_pie=json.dumps(status_pie),
        theme=theme,
    )


from flask import session

@app.context_processor
def inject_theme():
    return {"theme": session.get("theme", "light")}


@app.route("/people/<int:person_id>", methods=["GET"])
def person_view(person_id: int):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM people WHERE id = %s", (person_id,))
    person = cur.fetchone()
    if not person:
        cur.close()
        conn.close()
        return redirect(url_for("people"))

    cur.execute(
        """
        SELECT l.*,
               CASE
                   WHEN l.principal <= l.paid THEN 'Closed'
                   WHEN l.due_date < CURDATE() THEN 'Overdue'
                   ELSE 'Active'
               END AS status
        FROM loans l
        WHERE l.person_id = %s
        ORDER BY l.due_date IS NULL, l.due_date ASC, l.id DESC
        """,
        (person_id,),
    )
    loans_list = cur.fetchall()

    cur.close()
    conn.close()

    theme = session.get("theme", app.config["DEFAULT_THEME"])
    return render_template("person_view.html", person=person, loans=loans_list, theme=theme)


@app.route("/people/<int:person_id>/edit", methods=["POST"])
def person_edit(person_id: int):
    name = request.form["name"].strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    notes = request.form.get("notes", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE people
        SET name=%s, phone=%s, email=%s, notes=%s
        WHERE id=%s
        """,
        (name, phone, email, notes, person_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("people"))


@app.route("/people/<int:person_id>/delete", methods=["POST"])
def person_delete(person_id: int):
    conn = get_db_connection()
    cur = conn.cursor()

    # Prevent deletion if this person has loans (safer)
    cur.execute("SELECT COUNT(*) AS c FROM loans WHERE person_id=%s", (person_id,))
    has_loans = (cur.fetchone()["c"] or 0) > 0
    if has_loans:
        cur.close()
        conn.close()
        return redirect(url_for("people"))

    cur.execute("DELETE FROM people WHERE id=%s", (person_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("people"))


from datetime import date, datetime

def _days_overdue(due):
    if not due:
        return 0
    if isinstance(due, datetime):
        due = due.date()
    today = date.today()
    return (today - due).days if due < today else 0

@app.route("/loans/<int:loan_id>", methods=["GET"])
def loan_view(loan_id: int):
    conn = get_db_connection()
    cur = conn.cursor()

    # loan + person
    cur.execute(
        """
        SELECT l.*,
               p.name AS person_name,
               p.phone AS person_phone,
               p.email AS person_email
        FROM loans l
        JOIN people p ON p.id = l.person_id
        WHERE l.id = %s
        """,
        (loan_id,),
    )
    loan = cur.fetchone()
    if not loan:
        cur.close()
        conn.close()
        return redirect(url_for("loans"))

    # payments
    cur.execute(
        """
        SELECT id, paid_date, amount, note
        FROM payments
        WHERE loan_id = %s
        ORDER BY paid_date DESC, id DESC
        """,
        (loan_id,),
    )
    payments = cur.fetchall()

    # computed
    principal = int(loan["principal"] or 0)
    paid = int(loan["paid"] or 0)
    remaining = max(principal - paid, 0)

    due = loan.get("due_date")
    overdue_days = _days_overdue(due)

    if remaining <= 0:
        status = "Closed"
    elif overdue_days > 0:
        status = "Overdue"
    else:
        status = "Active"

    pct = 0
    if principal > 0:
        pct = round(min(paid / principal, 1.0) * 100)

    cur.close()
    conn.close()

    theme = session.get("theme", app.config.get("DEFAULT_THEME", "light"))
    return render_template(
        "loan_view.html",
        loan=loan,
        payments=payments,
        principal=principal,
        paid=paid,
        remaining=remaining,
        status=status,
        overdue_days=overdue_days,
        pct=pct,
        theme=theme,
    )


@app.route("/loans/<int:loan_id>/payments/add", methods=["POST"])
def payment_add(loan_id: int):
    paid_date = request.form.get("paid_date")
    amount = int(request.form.get("amount") or 0)
    note = request.form.get("note", "").strip()

    if amount <= 0:
        return redirect(url_for("loan_view", loan_id=loan_id))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO payments (loan_id, paid_date, amount, note) VALUES (%s, %s, %s, %s)",
        (loan_id, paid_date, amount, note),
    )
    cur.execute("UPDATE loans SET paid = paid + %s WHERE id = %s", (amount, loan_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("loan_view", loan_id=loan_id))



@app.route("/loans/<int:loan_id>/payments/<int:payment_id>/delete", methods=["POST"])
def payment_delete(loan_id: int, payment_id: int):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT amount FROM payments WHERE id=%s AND loan_id=%s", (payment_id, loan_id))
    row = cur.fetchone()
    if row:
        amt = int(row["amount"] or 0)
        cur.execute("DELETE FROM payments WHERE id=%s AND loan_id=%s", (payment_id, loan_id))
        cur.execute("UPDATE loans SET paid = GREATEST(paid - %s, 0) WHERE id=%s", (amt, loan_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("loan_view", loan_id=loan_id))


@app.route("/loans/<int:loan_id>/edit", methods=["POST"])
def loan_edit(loan_id: int):
    person_id = int(request.form["person"])
    direction = int(request.form["direction"])
    principal = float(request.form["principal"] or 0)
    paid = float(request.form.get("paid", 0) or 0)
    due_date = request.form["due_date"]
    given_date = request.form["given_date"]
    notes = request.form.get("notes", "")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE loans
        SET person_id=%s, direction=%s, principal=%s, paid=%s, given_date=%s, due_date=%s, notes=%s
        WHERE id=%s
        """,
        (person_id, direction, principal, paid, given_date, due_date, notes, loan_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("loans"))


@app.route("/loans/<int:loan_id>/delete", methods=["POST"])
def loan_delete(loan_id: int):
    conn = get_db_connection()
    cur = conn.cursor()

    # delete payments first (if you have FK constraints)
    cur.execute("DELETE FROM payments WHERE loan_id=%s", (loan_id,))
    cur.execute("DELETE FROM loans WHERE id=%s", (loan_id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("loans"))


if __name__ == "__main__":
    app.run(debug=app.config["FLASK_DEBUG"])
