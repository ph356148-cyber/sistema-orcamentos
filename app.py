from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
from datetime import datetime
from functools import wraps
from io import BytesIO

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "segredo"


# 🔒 LOGIN OBRIGATÓRIO
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

        c.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS financeiro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT,
            valor REAL,
            data TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            data TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            descricao TEXT,
            valor REAL,
            data TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS itens_orcamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            descricao TEXT,
            quantidade INTEGER,
            valor REAL
        )
        """)

criar_banco()


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


# 📊 DASHBOARD
@app.route("/dashboard")
@login_required
def dashboard():
    with conectar() as conn:
        c = conn.cursor()

        total = c.execute("SELECT SUM(valor) FROM financeiro").fetchone()[0] or 0
        total_orc = c.execute("SELECT SUM(valor) FROM orcamentos").fetchone()[0] or 0
        clientes = c.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        ag = c.execute("SELECT COUNT(*) FROM agendamentos").fetchone()[0]

    return render_template("dashboard.html",
        total=total,
        total_orcamentos=total_orc,
        total_clientes=clientes,
        total_agendamentos=ag
    )


# 👥 CLIENTES
@app.route("/clientes", methods=["GET", "POST"])
@login_required
def clientes():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            c.execute(
                "INSERT INTO clientes (nome, telefone) VALUES (?,?)",
                (request.form["nome"], request.form["telefone"])
            )
            conn.commit()

        lista = c.execute("SELECT * FROM clientes").fetchall()

    return render_template("clientes.html", clientes=lista)


@app.route("/deletar_cliente/<int:id>")
@login_required
def deletar_cliente(id):
    with conectar() as conn:
        conn.execute("DELETE FROM clientes WHERE id=?", (id,))
        conn.commit()
    return redirect("/clientes")


# 💰 FINANCEIRO
@app.route("/financeiro", methods=["GET", "POST"])
@login_required
def financeiro():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            c.execute(
                "INSERT INTO financeiro VALUES (NULL,?,?,?)",
                (
                    request.form["descricao"],
                    float(request.form["valor"]),
                    datetime.now().strftime("%d/%m/%Y")
                )
            )
            conn.commit()

        lista = c.execute("SELECT * FROM financeiro").fetchall()

    return render_template("financeiro.html", dados=lista)


@app.route("/deletar_financeiro/<int:id>")
@login_required
def deletar_financeiro(id):
    with conectar() as conn:
        conn.execute("DELETE FROM financeiro WHERE id=?", (id,))
        conn.commit()
    return redirect("/financeiro")


# 📅 AGENDAMENTOS
@app.route("/agendamentos", methods=["GET", "POST"])
@login_required
def agendamentos():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            c.execute(
                "INSERT INTO agendamentos VALUES (NULL,?,?)",
                (request.form["cliente_id"], request.form["data"])
            )
            conn.commit()

        lista = c.execute("""
            SELECT a.id, c.nome, a.data
            FROM agendamentos a
            JOIN clientes c ON a.cliente_id = c.id
        """).fetchall()

        clientes = c.execute("SELECT * FROM clientes").fetchall()

    return render_template("agendamentos.html", dados=lista, clientes=clientes)


# 🧾 ORÇAMENTOS
@app.route("/orcamentos", methods=["GET", "POST"])
@login_required
def orcamentos():
    with conectar() as conn:
        c = conn.cursor()

        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")

            if not cliente_id:
                return "Selecione um cliente"

            c.execute(
                "INSERT INTO orcamentos (cliente_id, descricao, valor, data) VALUES (?, ?, ?, ?)",
                (cliente_id, "", 0, datetime.now().isoformat())
            )

            orcamento_id = c.lastrowid

            descricoes = request.form.getlist("descricao[]")
            quantidades = request.form.getlist("quantidade[]")
            valores = request.form.getlist("valor[]")

            total = 0

            for d, q, v in zip(descricoes, quantidades, valores):
                if not d:
                    continue

                try:
                    q = int(q)
                    v = float(v)
                except:
                    continue

                subtotal = v
                total += subtotal

                c.execute(
                    """
                    INSERT INTO itens_orcamento 
                    (orcamento_id, descricao, quantidade, valor) 
                    VALUES (?, ?, ?, ?)
                    """,
                    (orcamento_id, d, q, v)
                )

            c.execute(
                "UPDATE orcamentos SET valor=? WHERE id=?",
                (total, orcamento_id)
            )

            conn.commit()

        lista = c.execute("""
            SELECT o.id, c.nome, o.valor, o.data
            FROM orcamentos o
            JOIN clientes c ON o.cliente_id = c.id
            ORDER BY o.id DESC
        """).fetchall()

        clientes = c.execute("SELECT * FROM clientes").fetchall()

    return render_template("orcamentos.html", lista=lista, clientes=clientes)


# 📄 GERAR PDF
@app.route("/gerar_pdf/<int:id>")
@login_required
def gerar_pdf(id):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    with conectar() as conn:
        c = conn.cursor()

        c.execute("""
            SELECT o.id, c.nome, o.valor
            FROM orcamentos o
            JOIN clientes c ON o.cliente_id = c.id
            WHERE o.id=?
        """, (id,))
        orc = c.fetchone()

        c.execute("""
            SELECT descricao, quantidade, valor 
            FROM itens_orcamento 
            WHERE orcamento_id=?
        """, (id,))
        itens = c.fetchall()

    elementos = []

    # 🔷 CABEÇALHO
    header = [
        ["ONE SISTEMAS DE SEGURANÇA", "", f"DATA: {datetime.now().strftime('%d/%m/%Y')}"],
        ["Sua segurança em primeiro lugar", "", f"COTAÇÃO #: {orc['id']}"],
        ["CNPJ: 50.750.565/0001-64", "", "Telefone: (61) 99380-4232"],
        ["Endereço: Rua F Q37 L1W - Formosa GO", "", "Email: onesistemasseguranca@gmail.com"],
    ]

    tabela_header = Table(header, colWidths=[250, 50, 200])
    elementos.append(tabela_header)
    elementos.append(Spacer(1, 15))

    # 🔷 CLIENTE
    cliente = [
        ["Cliente:", orc["nome"], "Validade:", "90 dias"],
        ["Técnico:", "Paulo / Rony", "", ""],
    ]

    tabela_cliente = Table(cliente, colWidths=[80, 200, 80, 100])
    elementos.append(tabela_cliente)
    elementos.append(Spacer(1, 20))

    # 🔷 TÍTULO
    elementos.append(Paragraph("<b>ORÇAMENTO</b>", styles["Heading2"]))
    elementos.append(Spacer(1, 10))

    # 🔷 ITENS
    dados = [["DESCRIÇÃO", "QTD", "VALOR (R$)"]]

    for i in itens:
        dados.append([
            i["descricao"],
            str(i["quantidade"]),
            f"{i['valor']:.2f}"
        ])

    tabela_itens = Table(dados, colWidths=[300, 60, 100])

    tabela_itens.setStyle([
        ("BACKGROUND", (0,0), (-1,0), (0.8,0.8,0.8)),
        ("GRID", (0,0), (-1,-1), 0.5, "black"),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
    ])

    elementos.append(tabela_itens)
    elementos.append(Spacer(1, 15))

    # 🔷 TOTAL
    total = Table(
        [["TOTAL:", f"R$ {orc['valor']:.2f}"]],
        colWidths=[350, 110]
    )

    total.setStyle([
        ("BACKGROUND", (0,0), (-1,-1), (0.9,0.9,0.9)),
        ("GRID", (0,0), (-1,-1), 1, "black"),
        ("ALIGN", (1,0), (1,0), "RIGHT"),
    ])

    elementos.append(total)
    elementos.append(Spacer(1, 20))

    # 🔷 CONDIÇÕES
    elementos.append(Paragraph(
        "Condições: Serviço válido por 90 dias • Materiais adicionais não inclusos • Pagamento a combinar",
        styles["Normal"]
    ))

    elementos.append(Spacer(1, 10))

    elementos.append(Paragraph(
        "OBS: Parcelamento em até 12x com juros da máquina",
        styles["Normal"]
    ))

    elementos.append(Spacer(1, 30))

    # 🔷 ASSINATURA
    assinatura = Table([
        ["__________________________", "", "__________________________"],
        ["Cliente", "", "Técnico"]
    ], colWidths=[200, 50, 200])

    elementos.append(assinatura)

    doc.build(elementos)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="orcamento.pdf")

# 🚀 RODAR
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)