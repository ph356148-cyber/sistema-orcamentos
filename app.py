from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
from datetime import datetime
from functools import wraps
from io import BytesIO

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "segredo"


# 🔒 LOGIN
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logado"):
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


# 🧠 BANCO
def conectar():
    conn = sqlite3.connect("banco.db")
    conn.row_factory = sqlite3.Row
    return conn


def criar_banco():
    with conectar() as conn:
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS financeiro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT,
            valor REAL,
            data TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            data TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            descricao TEXT,
            valor REAL,
            data TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS itens_orcamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            descricao TEXT,
            quantidade INTEGER,
            valor REAL
        )""")

        # 💸 CONTAS A PAGAR
        c.execute("""CREATE TABLE IF NOT EXISTS contas_pagar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT,
            valor REAL,
            data_vencimento TEXT,
            data_pagamento TEXT,
            status TEXT DEFAULT 'pendente'
        )""")

        # 💰 CONTAS A RECEBER
        c.execute("""CREATE TABLE IF NOT EXISTS contas_receber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT,
            valor REAL,
            data_vencimento TEXT,
            data_pagamento TEXT,
            status TEXT DEFAULT 'pendente'
        )""")


criar_banco()


# 💰 FORMATAR REAL
def formatar_real(valor):
    valor = valor or 0
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# 🔐 LOGIN
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["user"] == "paulo" and request.form["senha"] == "0147":
            session["logado"] = True
            return redirect("/dashboard")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# 📊 DASHBOARD PROFISSIONAL
@app.route("/dashboard")
@login_required
def dashboard():
    with conectar() as conn:
        c = conn.cursor()

        entradas = c.execute("SELECT SUM(valor) FROM financeiro").fetchone()[0] or 0

        saidas = c.execute("""
            SELECT SUM(valor) FROM contas_pagar
            WHERE status='pago'
        """).fetchone()[0] or 0

        a_pagar = c.execute("""
            SELECT SUM(valor) FROM contas_pagar
            WHERE status='pendente'
        """).fetchone()[0] or 0

        a_receber = c.execute("""
            SELECT SUM(valor) FROM contas_receber
            WHERE status='pendente'
        """).fetchone()[0] or 0

        saldo = entradas - saidas

    return render_template("dashboard.html",
        entradas=entradas,
        saidas=saidas,
        saldo=saldo,
        a_pagar=a_pagar,
        a_receber=a_receber,

        entradas_formatado=formatar_real(entradas),
        saidas_formatado=formatar_real(saidas),
        saldo_formatado=formatar_real(saldo),
        a_pagar_formatado=formatar_real(a_pagar),
        a_receber_formatado=formatar_real(a_receber)
    )


# 👥 CLIENTES
@app.route("/clientes", methods=["GET", "POST"])
@login_required
def clientes():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            c.execute("INSERT INTO clientes (nome, telefone) VALUES (?,?)",
                      (request.form["nome"], request.form["telefone"]))
            conn.commit()

        lista = c.execute("SELECT * FROM clientes").fetchall()

    return render_template("clientes.html", clientes=lista)


# 💰 FINANCEIRO (ENTRADAS)
@app.route("/financeiro", methods=["GET", "POST"])
@login_required
def financeiro():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            c.execute("INSERT INTO financeiro VALUES (NULL,?,?,?)",
                      (request.form["descricao"],
                       float(request.form["valor"]),
                       datetime.now().strftime("%d/%m/%Y")))
            conn.commit()

        lista = c.execute("SELECT * FROM financeiro").fetchall()

    return render_template("financeiro.html", dados=lista)


# 💸 CONTAS A PAGAR
@app.route("/contas_pagar", methods=["GET", "POST"])
@login_required
def contas_pagar():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            c.execute("""
                INSERT INTO contas_pagar (descricao, valor, data_vencimento)
                VALUES (?, ?, ?)
            """, (
                request.form["descricao"],
                float(request.form["valor"]),
                request.form["vencimento"]
            ))
            conn.commit()

        lista = c.execute("SELECT * FROM contas_pagar").fetchall()

    return render_template("contas_pagar.html", contas=lista)


@app.route("/pagar_conta/<int:id>")
@login_required
def pagar_conta(id):
    with conectar() as conn:
        conn.execute("""
            UPDATE contas_pagar
            SET status='pago', data_pagamento=?
            WHERE id=?
        """, (datetime.now().strftime("%Y-%m-%d"), id))
        conn.commit()

    return redirect("/contas_pagar")


# 💵 CONTAS A RECEBER
@app.route("/contas_receber")
@login_required
def contas_receber():
    with conectar() as conn:
        lista = conn.execute("SELECT * FROM contas_receber").fetchall()
    return render_template("contas_receber.html", contas=lista)


@app.route("/receber/<int:id>")
@login_required
def receber(id):
    with conectar() as conn:
        conn.execute("""
            UPDATE contas_receber
            SET status='pago', data_pagamento=?
            WHERE id=?
        """, (datetime.now().strftime("%Y-%m-%d"), id))
        conn.commit()
    return redirect("/contas_receber")


# 🧾 ORÇAMENTOS (CORRIGIDO)
@app.route("/orcamentos", methods=["GET", "POST"])
@login_required
def orcamentos():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")

            c.execute("INSERT INTO orcamentos VALUES (NULL,?,?,?,?)",
                      (cliente_id, "", 0, datetime.now().isoformat()))

            orcamento_id = c.lastrowid

            descricoes = request.form.getlist("descricao[]")
            quantidades = request.form.getlist("quantidade[]")
            valores = request.form.getlist("valor[]")

            total = 0

            for d, q, v in zip(descricoes, quantidades, valores):
                try:
                    q = int(q)
                    v = float(v)
                except:
                    continue

                subtotal = q * v
                total += subtotal

                c.execute("""
                    INSERT INTO itens_orcamento
                    (orcamento_id, descricao, quantidade, valor)
                    VALUES (?, ?, ?, ?)
                """, (orcamento_id, d, q, v))

            c.execute("UPDATE orcamentos SET valor=? WHERE id=?",
                      (total, orcamento_id))

            # 💰 vira conta a receber automática
            c.execute("""
                INSERT INTO contas_receber (descricao, valor, data_vencimento)
                VALUES (?, ?, ?)
            """, (f"Orçamento #{orcamento_id}", total,
                  datetime.now().strftime("%Y-%m-%d")))

            conn.commit()

        lista = c.execute("""
            SELECT o.id, c.nome, o.valor
            FROM orcamentos o
            JOIN clientes c ON o.cliente_id = c.id
        """).fetchall()

        clientes = c.execute("SELECT * FROM clientes").fetchall()

    return render_template("orcamentos.html", lista=lista, clientes=clientes)


# 🚀 RODAR
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
