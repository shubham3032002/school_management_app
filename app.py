"""School Management System - run with:  python app.py"""
import os
from datetime import date, timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "change-me"),
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///school.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)
SCHOOL = os.getenv("SCHOOL_NAME", "Greenfield High School")
db = SQLAlchemy(app)


# ───────────────────────── Models (simplified from the PostgreSQL schema) ─────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # PRINCIPAL ADMIN TEACHER ACCOUNTANT


class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    academic_year = db.Column(db.String(10), default="2026-27")
    class_teacher = db.Column(db.String(100))
    capacity = db.Column(db.Integer)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admission_no = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(1))
    dob = db.Column(db.Date)
    section_id = db.Column(db.Integer, db.ForeignKey("section.id"))
    guardian = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default="ACTIVE")
    section = db.relationship("Section")

    @property
    def sec(self):
        return self.section.name if self.section else "-"


class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_no = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    staff_type = db.Column(db.String(20), default="TEACHER")
    designation = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    on_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)  # PRESENT ABSENT LATE


class Homework(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey("section.id"))
    subject = db.Column(db.String(80))
    due_date = db.Column(db.Date)
    max_marks = db.Column(db.Float)
    section = db.relationship("Section")

    @property
    def sec(self):
        return self.section.name if self.section else "-"


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    exam_type = db.Column(db.String(20), default="UNIT_TEST")
    start_date = db.Column(db.Date)
    status = db.Column(db.String(15), default="DRAFT")  # DRAFT SCHEDULED MARKS_ENTRY VERIFIED PUBLISHED


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"))
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    subject = db.Column(db.String(80))
    marks = db.Column(db.Float)
    max_marks = db.Column(db.Float, default=100)


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(30), unique=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    title = db.Column(db.String(150))
    net = db.Column(db.Float, default=0)
    paid = db.Column(db.Float, default=0)
    due_date = db.Column(db.Date)
    student = db.relationship("Student")

    @property
    def who(self):
        return self.student.name if self.student else "-"

    @property
    def balance(self):
        return round(self.net - self.paid, 2)

    @property
    def status(self):
        return "PAID" if self.paid >= self.net else "PARTIAL" if self.paid > 0 else "UNPAID"


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"))
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(15))
    paid_on = db.Column(db.Date, default=date.today)


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    audience = db.Column(db.String(15), default="ALL")
    created_on = db.Column(db.Date, default=date.today)


# ───────────────────────── Access control ─────────────────────────
NAV = [("dashboard", "Dashboard", "/"), ("students", "Students", "/m/students"), ("staff", "Staff", "/m/staff"),
       ("sections", "Classes", "/m/sections"), ("attendance", "Attendance", "/attendance"),
       ("homework", "Homework", "/m/homework"), ("exams", "Exams", "/m/exams"),
       ("fees", "Fees", "/m/fees"), ("announcements", "Notices", "/m/announcements")]
ACCESS = {
    "PRINCIPAL": {n[0] for n in NAV}, "ADMIN": {n[0] for n in NAV},
    "TEACHER": {"dashboard", "students", "attendance", "homework", "exams", "announcements"},
    "ACCOUNTANT": {"dashboard", "students", "fees", "announcements"},
}


def guard(module):
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login"))
            if module not in ACCESS.get(u.role, set()):
                abort(403)
            return fn(*a, **kw)
        return inner
    return deco


def current_user():
    return db.session.get(User, session["uid"]) if "uid" in session else None


@app.context_processor
def inject():
    u = current_user()
    nav = [n for n in NAV if u and n[0] in ACCESS.get(u.role, set())]
    return dict(user=u, nav=nav, school=SCHOOL, path=request.path)


# ───────────────────────── Module config (drives list + create forms) ─────────────────────────
def opts(model, label):
    return [(r.id, label(r)) for r in model.query.order_by(model.id)]


def modules():
    secs = opts(Section, lambda s: s.name)
    studs = opts(Student, lambda s: f"{s.name} ({s.admission_no})")
    return {
        "students": dict(model=Student, title="Students", mod="students",
            cols=[("Adm. no", "admission_no"), ("Name", "name"), ("Class", "sec"), ("Guardian", "guardian"), ("Phone", "phone"), ("Status", "status")],
            forms=[dict(action="/m/students", title="Admit a student", fields=[
                ("admission_no", "Admission no", "text", None), ("name", "Full name", "text", None),
                ("gender", "Gender", "select", [("M", "Male"), ("F", "Female"), ("O", "Other")]),
                ("dob", "Date of birth", "date", None), ("section_id", "Class", "select", secs),
                ("guardian", "Parent / guardian", "text", None), ("phone", "Phone", "text", None)])]),
        "staff": dict(model=Staff, title="Staff", mod="staff",
            cols=[("Emp. no", "employee_no"), ("Name", "name"), ("Role", "staff_type"), ("Designation", "designation"), ("Phone", "phone")],
            forms=[dict(action="/m/staff", title="Add a staff member", fields=[
                ("employee_no", "Employee no", "text", None), ("name", "Full name", "text", None),
                ("staff_type", "Role", "select", [(x, x.title()) for x in ("TEACHER", "ADMIN", "ACCOUNTANT", "PRINCIPAL", "OTHER")]),
                ("designation", "Designation", "text", None), ("phone", "Phone", "text", None), ("email", "Email", "text", None)])]),
        "sections": dict(model=Section, title="Classes & sections", mod="sections",
            cols=[("Section", "name"), ("Year", "academic_year"), ("Class teacher", "class_teacher"), ("Capacity", "capacity")],
            forms=[dict(action="/m/sections", title="Add a section", fields=[
                ("name", "Section (e.g. 8-A)", "text", None), ("academic_year", "Academic year", "text", None),
                ("class_teacher", "Class teacher", "text", None), ("capacity", "Capacity", "number", None)])]),
        "homework": dict(model=Homework, title="Homework", mod="homework",
            cols=[("Title", "title"), ("Class", "sec"), ("Subject", "subject"), ("Due", "due_date"), ("Marks", "max_marks")],
            forms=[dict(action="/m/homework", title="Assign homework", fields=[
                ("title", "Title", "text", None), ("section_id", "Class", "select", secs), ("subject", "Subject", "text", None),
                ("due_date", "Due date", "date", None), ("max_marks", "Max marks", "number", None)])]),
        "exams": dict(model=Exam, title="Exams", mod="exams", link=("Enter marks", "/exams/{id}/marks"),
            cols=[("Exam", "name"), ("Type", "exam_type"), ("Starts", "start_date"), ("Status", "status")],
            forms=[dict(action="/m/exams", title="Schedule an exam", fields=[
                ("name", "Exam name", "text", None),
                ("exam_type", "Type", "select", [(x, x.replace("_", " ").title()) for x in ("UNIT_TEST", "MID_TERM", "FINAL", "PRACTICAL", "OTHER")]),
                ("start_date", "Start date", "date", None),
                ("status", "Status", "select", [(x, x.replace("_", " ").title()) for x in ("DRAFT", "SCHEDULED", "MARKS_ENTRY", "VERIFIED", "PUBLISHED")])])]),
        "fees": dict(model=Invoice, title="Fees", mod="fees",
            cols=[("Invoice", "invoice_no"), ("Student", "who"), ("For", "title"), ("Amount", "net"), ("Paid", "paid"), ("Balance", "balance"), ("Due", "due_date"), ("Status", "status")],
            forms=[dict(action="/m/fees", title="Raise an invoice", fields=[
                ("student_id", "Student", "select", studs), ("title", "Title (e.g. Term 1 fees)", "text", None),
                ("net", "Amount (₹)", "number", None), ("due_date", "Due date", "date", None)]),
                dict(action="/fees/pay", title="Record a payment", fields=[
                    ("invoice_id", "Invoice", "select", [(i.id, f"{i.invoice_no} · {i.who} · ₹{i.balance:g} due") for i in Invoice.query.all() if i.balance > 0]),
                    ("amount", "Amount (₹)", "number", None),
                    ("method", "Method", "select", [(x, x.title()) for x in ("CASH", "UPI", "CARD", "CHEQUE", "NET_BANKING")])])]),
        "announcements": dict(model=Announcement, title="Notices", mod="announcements",
            cols=[("Title", "title"), ("Audience", "audience"), ("Posted", "created_on")],
            forms=[dict(action="/m/announcements", title="Post a notice", fields=[
                ("title", "Title", "text", None), ("body", "Message", "textarea", None),
                ("audience", "Audience", "select", [(x, x.title()) for x in ("ALL", "STAFF", "STUDENTS", "PARENTS")])])]),
    }


def coerce(model, key, val):
    if val in (None, ""):
        return None
    t = type(model.__table__.c[key].type).__name__
    return date.fromisoformat(val) if t == "Date" else int(val) if t == "Integer" else float(val) if t == "Float" else val


@app.route("/m/<key>", methods=["GET", "POST"])
def module(key):
    cfg = modules().get(key)
    u = current_user()
    if not cfg:
        abort(404)
    if not u:
        return redirect(url_for("login"))
    if cfg["mod"] not in ACCESS.get(u.role, set()):
        abort(403)
    if request.method == "POST":
        try:
            data = {n: coerce(cfg["model"], n, request.form.get(n)) for f in cfg["forms"][:1] for n, *_ in f["fields"]}
            if key == "fees":
                data["invoice_no"] = f"INV-{Invoice.query.count() + 1:05d}"
            db.session.add(cfg["model"](**data))
            db.session.commit()
            flash("Saved.", "ok")
        except Exception as e:  # duplicate admission no, bad number, etc.
            db.session.rollback()
            flash(f"Could not save: {str(e).splitlines()[0][:140]}", "err")
        return redirect(request.path)
    q = request.args.get("q", "").lower()
    rows = cfg["model"].query.order_by(cfg["model"].id.desc()).all()
    if q:
        rows = [r for r in rows if q in " ".join(str(getattr(r, c[1])) for c in cfg["cols"]).lower()]
    return render_template("module", cfg=cfg, rows=rows, q=q, title=cfg["title"], active=cfg["mod"])


@app.post("/fees/pay")
@guard("fees")
def pay():
    inv = db.session.get(Invoice, int(request.form["invoice_id"]))
    amt = float(request.form["amount"])
    if not inv or amt <= 0 or amt > inv.balance:
        flash("Enter an amount between 0 and the invoice balance.", "err")
    else:
        inv.paid += amt
        db.session.add(Payment(invoice_id=inv.id, amount=amt, method=request.form["method"]))
        db.session.commit()
        flash(f"Recorded ₹{amt:g} against {inv.invoice_no}.", "ok")
    return redirect("/m/fees")


# ───────────────────────── Attendance ─────────────────────────
@app.route("/attendance", methods=["GET", "POST"])
@guard("attendance")
def attendance():
    sid = request.values.get("section", type=int)
    day = date.fromisoformat(request.values.get("day") or date.today().isoformat())
    students = Student.query.filter_by(section_id=sid, status="ACTIVE").order_by(Student.name).all() if sid else []
    marks = {a.student_id: a for a in Attendance.query.filter(Attendance.on_date == day, Attendance.student_id.in_([s.id for s in students])).all()} if students else {}
    if request.method == "POST":
        for s in students:
            st = request.form.get(f"s{s.id}", "PRESENT")
            if s.id in marks:
                marks[s.id].status = st
            else:
                db.session.add(Attendance(student_id=s.id, on_date=day, status=st))
        db.session.commit()
        flash(f"Attendance saved for {len(students)} students.", "ok")
        return redirect(url_for("attendance", section=sid, day=day))
    return render_template("attendance", sections=Section.query.all(), sid=sid, day=day, students=students, marks=marks, title="Attendance", active="attendance")


# ───────────────────────── Exam marks ─────────────────────────
@app.route("/exams/<int:eid>/marks", methods=["GET", "POST"])
@guard("exams")
def marks(eid):
    exam = db.get_or_404(Exam, eid)
    sid = request.values.get("section", type=int)
    subject = (request.values.get("subject") or "").strip()
    mx = request.values.get("max", 100, type=float)
    students = Student.query.filter_by(section_id=sid).order_by(Student.name).all() if sid else []
    ready = bool(students and subject)
    existing = {r.student_id: r for r in Result.query.filter_by(exam_id=eid, subject=subject)} if ready else {}
    if request.method == "POST" and ready:
        for s in students:
            v = request.form.get(f"m{s.id}")
            if v in (None, ""):
                continue
            r = existing.get(s.id) or Result(exam_id=eid, student_id=s.id, subject=subject)
            r.marks, r.max_marks = float(v), mx
            db.session.add(r)
        db.session.commit()
        flash("Marks saved.", "ok")
        return redirect(url_for("marks", eid=eid, section=sid, subject=subject, max=mx))
    return render_template("marks", exam=exam, sections=Section.query.all(), sid=sid, subject=subject, mx=mx,
                           students=students, ready=ready, existing=existing, title=exam.name, active="exams")


# ───────────────────────── Dashboard & auth ─────────────────────────
@app.route("/")
@guard("dashboard")
def dashboard():
    today = date.today()
    att = Attendance.query.filter_by(on_date=today).all()
    present = sum(a.status in ("PRESENT", "LATE") for a in att)
    invoices = Invoice.query.all()
    stats = dict(
        students=Student.query.filter_by(status="ACTIVE").count(), staff=Staff.query.count(),
        att=f"{present * 100 // len(att)}%" if att else "Not marked",
        collected=sum(p.amount for p in Payment.query.all()), due=sum(i.balance for i in invoices))
    overdue = sorted([i for i in invoices if i.balance > 0 and i.due_date and i.due_date < today], key=lambda i: i.due_date)[:5]
    return render_template("dashboard", s=stats, overdue=overdue, today=today, title="Dashboard", active="dashboard",
                           notices=Announcement.query.order_by(Announcement.id.desc()).limit(4).all(),
                           homework=Homework.query.filter(Homework.due_date >= today).order_by(Homework.due_date).limit(5).all())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"].strip().lower()).first()
        if u and check_password_hash(u.password_hash, request.form["password"]):
            session["uid"] = u.id
            return redirect("/")
        flash("Wrong username or password.", "err")
    return render_template("login", title="Sign in")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.errorhandler(403)
def forbidden(_):
    return render_template("msg", title="No access", text="Your role doesn't include this section. Ask an admin if you need it."), 403


@app.errorhandler(404)
def missing(_):
    return render_template("msg", title="Not found", text="That page doesn't exist."), 404


# ───────────────────────── Templates ─────────────────────────
CSS = """
:root{--board:#1c3a35;--board2:#26504a;--chalk:#eef3ef;--paper:#f4f6f5;--ink:#1a2926;--mute:#667572;--line:#d9e0dd;--gold:#e9c24a;--red:#b8412f;--green:#2f7a52}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 Figtree,system-ui,sans-serif;color:var(--ink);background:var(--paper);display:flex;min-height:100vh}
aside.nav{width:220px;background:var(--board);color:var(--chalk);padding:22px 14px;position:sticky;top:0;height:100vh;flex-shrink:0;display:flex;flex-direction:column}
aside.nav h2{font-size:17px;margin:0 8px 22px;line-height:1.25}aside.nav h2 small{display:block;font-weight:400;opacity:.65;font-size:12px;margin-top:2px}
aside.nav a{display:block;color:var(--chalk);text-decoration:none;padding:8px 10px;border-radius:6px;opacity:.82}
aside.nav a:hover{background:var(--board2);opacity:1}aside.nav a.on{background:var(--board2);opacity:1;box-shadow:inset 3px 0 var(--gold)}
.me{margin-top:auto;padding:10px;font-size:13px;border-top:1px solid #ffffff22}.me a{padding:4px 0;display:inline;text-decoration:underline}
main{flex:1;padding:28px 34px;max-width:1280px;min-width:0}
h1{font-size:26px;margin:0}h3{margin:0 0 12px;font-size:16px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:12px;flex-wrap:wrap}
input,select,textarea,button{font:inherit}input,select,textarea{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink)}
input:focus,select:focus,textarea:focus,button:focus-visible,a:focus-visible{outline:2px solid var(--board2);outline-offset:1px}
button,.btn{background:var(--board);color:#fff;border:0;padding:9px 16px;border-radius:6px;cursor:pointer;font-weight:600;text-decoration:none;display:inline-block}
button:hover,.btn:hover{background:var(--board2)}.search{display:flex;gap:8px}.search input{width:220px}
.split{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:22px;align-items:start}
.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px;margin-bottom:18px;overflow-x:auto}
table{border-collapse:collapse;width:100%}th{text-align:left;font-size:13px;color:var(--mute);font-weight:600;padding:8px 10px;border-bottom:2px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line)}tr:last-child td{border:0}tr:hover td{background:#f8faf9}
label{display:block;font-size:13px;color:var(--mute);margin:10px 0 3px}form button{margin-top:14px;width:100%}
.pill{padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;background:#e6ebe9}.PAID,.ACTIVE,.PUBLISHED,.PRESENT{background:#d9efe2;color:var(--green)}
.UNPAID,.ABSENT,.DROPPED{background:#f6dcd6;color:var(--red)}.PARTIAL,.LATE,.MARKS_ENTRY{background:#f8ecc4;color:#85670a}
.flash{padding:10px 14px;border-radius:6px;margin-bottom:16px}.flash.ok{background:#d9efe2}.flash.err{background:#f6dcd6}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:20px}
.stat{background:#fff;border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:8px;padding:14px 16px}.stat b{font-size:24px;display:block}.stat span{color:var(--mute);font-size:13px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.empty{color:var(--mute);padding:8px 0}.note{color:var(--mute);font-size:13px}
.radios{display:flex;gap:6px}.radios label{margin:0;display:flex;align-items:center;gap:4px;color:var(--ink);font-size:14px;padding:3px 9px;border:1px solid var(--line);border-radius:6px;cursor:pointer}
.radios input{width:auto}.row{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-bottom:16px}.row>div{flex:1;min-width:140px}.row button{width:auto;margin:0}
.login{margin:auto;width:360px;background:#fff;border:1px solid var(--line);border-top:5px solid var(--board);border-radius:8px;padding:30px}
.login h1{font-size:22px}.login p{color:var(--mute);margin:4px 0 18px}
@media(max-width:900px){body{flex-direction:column}aside.nav{width:100%;height:auto;position:static;flex-direction:row;flex-wrap:wrap;padding:10px}aside.nav h2,.me{display:none}
main{padding:18px}.split,.two{grid-template-columns:1fr}}
"""

T = {}
T["base"] = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{{ title }} - {{ school }}</title><link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap" rel=stylesheet>
<style>""" + CSS + """</style></head><body>
{% if user %}<aside class=nav><h2>{{ school }}<small>Academic year 2026-27</small></h2>
{% for k,l,u in nav %}<a href="{{ u }}" class="{{ 'on' if k==active }}">{{ l }}</a>{% endfor %}
<div class=me>{{ user.name }}<br><span style="opacity:.65">{{ user.role.title() }}</span> · <a href="/logout">Sign out</a></div></aside>{% endif %}
<main {% if not user %}style="display:flex"{% endif %}>
{% for c,m in get_flashed_messages(with_categories=true) %}<div class="flash {{ c }}">{{ m }}</div>{% endfor %}
{% block body %}{% endblock %}</main></body></html>"""

T["login"] = """{% extends 'base' %}{% block body %}<form class=login method=post>
<h1>{{ school }}</h1><p>Sign in to the school office.</p>
<label>Username</label><input name=username autofocus required><label>Password</label><input name=password type=password required>
<button>Sign in</button></form>{% endblock %}"""

T["msg"] = """{% extends 'base' %}{% block body %}<div class=panel><h1>{{ title }}</h1><p>{{ text }}</p><a class=btn href="/">Back to dashboard</a></div>{% endblock %}"""

T["module"] = """{% extends 'base' %}{% block body %}
<div class=top><h1>{{ cfg.title }}</h1><form class=search><input name=q value="{{ q }}" placeholder="Search {{ cfg.title|lower }}"><button style="margin:0;width:auto">Search</button></form></div>
<div class=split><div class=panel><table><tr>{% for l,a in cfg.cols %}<th>{{ l }}</th>{% endfor %}{% if cfg.link %}<th></th>{% endif %}</tr>
{% for r in rows %}<tr>{% for l,a in cfg.cols %}{% set v = r|attr(a) %}
<td>{% if l=='Status' %}<span class="pill {{ v }}">{{ v|replace('_',' ')|title }}</span>{% elif v is none %}-{% else %}{{ v }}{% endif %}</td>{% endfor %}
{% if cfg.link %}<td><a href="{{ cfg.link[1].format(id=r.id) }}">{{ cfg.link[0] }}</a></td>{% endif %}</tr>
{% else %}<tr><td colspan=9 class=empty>Nothing here yet. Use the form on the right to add the first one.</td></tr>{% endfor %}</table></div>
<div>{% for f in cfg.forms %}<form class=panel method=post action="{{ f.action }}"><h3>{{ f.title }}</h3>
{% for n,l,t,o in f.fields %}<label for="{{ f.action }}{{ n }}">{{ l }}</label>
{% if t=='select' %}<select name={{ n }} required>{% for v,x in o %}<option value="{{ v }}">{{ x }}</option>{% endfor %}</select>
{% elif t=='textarea' %}<textarea name={{ n }} rows=3></textarea>
{% else %}<input name={{ n }} type={{ t }} {% if t=='number' %}step=any{% endif %} {% if n in ('name','title','admission_no','employee_no','amount','net') %}required{% endif %}>{% endif %}{% endfor %}
<button>{{ f.title.split()[0] }}</button></form>{% endfor %}</div></div>{% endblock %}"""

T["attendance"] = """{% extends 'base' %}{% block body %}<div class=top><h1>Attendance</h1></div>
<form class=row method=get><div><label>Class</label><select name=section>{% for s in sections %}<option value={{ s.id }} {{ 'selected' if s.id==sid }}>{{ s.name }}</option>{% endfor %}</select></div>
<div><label>Date</label><input type=date name=day value="{{ day }}"></div><button>Load register</button></form>
{% if students %}<form method=post class=panel><input type=hidden name=section value={{ sid }}><input type=hidden name=day value="{{ day }}">
<table><tr><th>Student</th><th>Adm. no</th><th>Mark</th></tr>{% for s in students %}{% set cur = marks[s.id].status if s.id in marks else 'PRESENT' %}
<tr><td>{{ s.name }}</td><td>{{ s.admission_no }}</td><td><div class=radios>{% for v in ('PRESENT','ABSENT','LATE') %}
<label><input type=radio name="s{{ s.id }}" value={{ v }} {{ 'checked' if cur==v }}>{{ v.title() }}</label>{% endfor %}</div></td></tr>{% endfor %}</table>
<button style="width:auto">Save attendance</button></form>
{% else %}<div class=panel><p class=empty>{{ 'No active students in this class.' if sid else 'Pick a class and date to open its register.' }}</p></div>{% endif %}{% endblock %}"""

T["marks"] = """{% extends 'base' %}{% block body %}<div class=top><h1>{{ exam.name }}: marks</h1><a href="/m/exams">Back to exams</a></div>
<form class=row method=get><div><label>Class</label><select name=section>{% for s in sections %}<option value={{ s.id }} {{ 'selected' if s.id==sid }}>{{ s.name }}</option>{% endfor %}</select></div>
<div><label>Subject</label><input name=subject value="{{ subject }}" required></div><div><label>Max marks</label><input name=max type=number value="{{ mx|int }}"></div><button>Open sheet</button></form>
{% if ready %}<form method=post class=panel><input type=hidden name=section value={{ sid }}><input type=hidden name=subject value="{{ subject }}"><input type=hidden name=max value={{ mx }}>
<table><tr><th>Student</th><th style="width:140px">Marks / {{ mx|int }}</th></tr>{% for s in students %}
<tr><td>{{ s.name }}</td><td><input name="m{{ s.id }}" type=number step=any max={{ mx }} min=0 value="{{ existing[s.id].marks if s.id in existing }}"></td></tr>{% endfor %}</table>
<button style="width:auto">Save marks</button></form>{% else %}<div class=panel><p class=empty>Choose a class and subject to enter marks.</p></div>{% endif %}{% endblock %}"""

T["dashboard"] = """{% extends 'base' %}{% block body %}<div class=top><h1>Good day, {{ user.name.split()[0] }}</h1><span class=note>{{ today.strftime('%A, %d %B %Y') }}</span></div>
<div class=stats><div class=stat><b>{{ s.students }}</b><span>Active students</span></div><div class=stat><b>{{ s.staff }}</b><span>Staff members</span></div>
<div class=stat><b>{{ s.att }}</b><span>Present today</span></div><div class=stat><b>₹{{ '{:,.0f}'.format(s.collected) }}</b><span>Fees collected</span></div>
<div class=stat><b>₹{{ '{:,.0f}'.format(s.due) }}</b><span>Fees outstanding</span></div></div>
<div class=two><div class=panel><h3>Overdue fees</h3>{% if overdue %}<table>{% for i in overdue %}<tr><td>{{ i.who }}<br><span class=note>{{ i.title }}</span></td><td>₹{{ '{:,.0f}'.format(i.balance) }}</td><td class=note>due {{ i.due_date }}</td></tr>{% endfor %}</table>{% else %}<p class=empty>No overdue invoices.</p>{% endif %}</div>
<div class=panel><h3>Homework due soon</h3>{% if homework %}<table>{% for h in homework %}<tr><td>{{ h.title }}<br><span class=note>{{ h.sec }} · {{ h.subject }}</span></td><td class=note>{{ h.due_date }}</td></tr>{% endfor %}</table>{% else %}<p class=empty>Nothing due.</p>{% endif %}</div></div>
<div class=panel><h3>Latest notices</h3>{% for n in notices %}<p style="margin:0 0 10px"><b>{{ n.title }}</b> <span class=note>{{ n.created_on }}</span><br>{{ n.body }}</p>{% else %}<p class=empty>No notices posted.</p>{% endfor %}</div>{% endblock %}"""

app.jinja_loader = DictLoader(T)


# ───────────────────────── Demo data ─────────────────────────
def seed():
    if User.query.first():
        return
    pw = generate_password_hash(os.getenv("SEED_PASSWORD", "school123"))
    db.session.add_all([User(username=u, password_hash=pw, name=n, role=r) for u, n, r in [
        ("principal", "Meera Kulkarni", "PRINCIPAL"), ("admin", "Rahul Patil", "ADMIN"),
        ("teacher", "Anita Deshmukh", "TEACHER"), ("accountant", "Suresh Jadhav", "ACCOUNTANT")]])
    secs = [Section(name=n, class_teacher=t, capacity=40) for n, t in [("10-A", "Anita Deshmukh"), ("10-B", "Vikram Shinde"), ("9-A", "Pooja More")]]
    db.session.add_all(secs)
    db.session.add_all([Staff(employee_no=f"E{100+i}", name=n, staff_type=t, designation=d, phone="98220000%02d" % i)
                        for i, (n, t, d) in enumerate([("Anita Deshmukh", "TEACHER", "Mathematics"), ("Vikram Shinde", "TEACHER", "Science"),
                                                       ("Pooja More", "TEACHER", "English"), ("Suresh Jadhav", "ACCOUNTANT", "Accounts Officer")])])
    db.session.flush()
    names = ["Aarav Patil", "Isha Kulkarni", "Omkar Jadhav", "Sneha Pawar", "Rohan Chavan", "Diya Shah", "Kabir Mane", "Tanvi Joshi", "Arjun Kale",
             "Riya Gaikwad", "Yash Bhosale", "Nisha Rane"]
    studs = [Student(admission_no=f"A{2601+i}", name=n, gender="F" if i % 2 else "M", dob=date(2011, 1 + i % 12, 5 + i),
                     section_id=secs[i % 3].id, guardian=n.split()[1] + " (Parent)", phone="97650000%02d" % i) for i, n in enumerate(names)]
    db.session.add_all(studs)
    db.session.flush()
    today = date.today()
    for i, s in enumerate(studs):
        inv = Invoice(invoice_no=f"INV-{i+1:05d}", student_id=s.id, title="Term 1 fees", net=18500, paid=[18500, 0, 9000][i % 3],
                      due_date=today + timedelta(days=(-20 if i % 3 else 15)))
        db.session.add(inv)
    db.session.add_all([
        Homework(title="Quadratic equations: exercise 4.2", section_id=secs[0].id, subject="Mathematics", due_date=today + timedelta(days=3), max_marks=20),
        Homework(title="Lab report: acids and bases", section_id=secs[1].id, subject="Science", due_date=today + timedelta(days=5), max_marks=25),
        Exam(name="Unit Test 1", exam_type="UNIT_TEST", start_date=today + timedelta(days=12), status="SCHEDULED"),
        Exam(name="Mid Term", exam_type="MID_TERM", start_date=today + timedelta(days=60), status="DRAFT"),
        Announcement(title="Parent-teacher meeting", body="Held this Saturday from 10 am in the main hall. Report cards will be shared.", audience="PARENTS"),
        Announcement(title="Annual day rehearsals", body="Rehearsals begin Monday after lunch break. Class teachers will share the schedule.", audience="ALL")])
    db.session.commit()


with app.app_context():
    db.create_all()
    seed()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG", "1") == "1")
