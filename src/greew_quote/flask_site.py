from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
import os
from pathlib import Path
from typing import Any, Callable

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
import psycopg
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

from .engine import QuoteInput, build_client_message, calculate_quote, format_brl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MASTER_USERNAME = os.getenv("GREEW_MASTER_USER", "master").strip().lower()
MASTER_PASSWORD = os.getenv("GREEW_MASTER_PASSWORD", "Master@123")
MASTER_NAME = os.getenv("GREEW_MASTER_NAME", "Master")
SECRET_KEY = os.getenv("GREEW_SECRET_KEY", "dev-change-this-key")

CITIES = ["Sao Paulo", "Belem", "Manaus", "Macapa", "Boa Vista", "Fortaleza"]
PRICE_MODES = {
    "cheio": "Valor cheio",
    "justo": "Valor justo (recomendado)",
    "desconto": "Desconto máximo",
}


def _to_decimal(value: str) -> Decimal:
    cleaned = value.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def _to_meters(value: Decimal, unit: str) -> Decimal:
    if unit == "cm":
        return value / Decimal("100")
    return value


def _build_cubage_from_rows(unit: str, form: Any) -> tuple[int, Decimal]:
    qty_list = form.getlist("volume_qty[]")
    length_list = form.getlist("volume_length[]")
    width_list = form.getlist("volume_width[]")
    height_list = form.getlist("volume_height[]")

    if not qty_list:
        raise ValueError("Adicione ao menos um volume.")
    if not (len(qty_list) == len(length_list) == len(width_list) == len(height_list)):
        raise ValueError("Dados de volumes inconsistentes.")

    total_cubage = Decimal("0")
    total_volumes = 0
    for idx, (qty_raw, length_raw, width_raw, height_raw) in enumerate(
        zip(qty_list, length_list, width_list, height_list),
        start=1,
    ):
        try:
            qty = int(str(qty_raw).strip())
        except ValueError as exc:
            raise ValueError(f"Quantidade inválida no volume {idx}.") from exc
        if qty <= 0:
            raise ValueError(f"Quantidade deve ser maior que zero no volume {idx}.")

        length = _to_decimal(str(length_raw))
        width = _to_decimal(str(width_raw))
        height = _to_decimal(str(height_raw))
        if length <= 0 or width <= 0 or height <= 0:
            raise ValueError(f"Dimensões devem ser maiores que zero no volume {idx}.")

        length_m = _to_meters(length, unit)
        width_m = _to_meters(width, unit)
        height_m = _to_meters(height, unit)

        total_cubage += length_m * width_m * height_m * Decimal(qty)
        total_volumes += qty

    return total_volumes, total_cubage


def _selected_price(result: Any, mode: str) -> Decimal:
    if mode == "cheio":
        return result.full_price
    if mode == "desconto":
        return result.max_discount_price
    return result.fair_price


def _connect() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("Defina DATABASE_URL com a string de conexão do Neon.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _init_db() -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_master BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                id BIGSERIAL PRIMARY KEY,
                quote_code TEXT NOT NULL UNIQUE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                volumes INTEGER NOT NULL,
                weight_total_kg NUMERIC(14,2) NOT NULL,
                cubage_total_m3 NUMERIC(14,2) NOT NULL,
                nf_value NUMERIC(14,2) NOT NULL,
                base_cubage NUMERIC(14,2) NOT NULL,
                base_weight NUMERIC(14,2) NOT NULL,
                base_nf NUMERIC(14,2) NOT NULL,
                average_simple NUMERIC(14,2) NOT NULL,
                average_weighted NUMERIC(14,2) NOT NULL,
                full_price NUMERIC(14,2) NOT NULL,
                fair_price NUMERIC(14,2) NOT NULL,
                max_discount_price NUMERIC(14,2) NOT NULL,
                strategy_note TEXT NOT NULL,
                client_price_mode TEXT NOT NULL,
                client_price NUMERIC(14,2) NOT NULL,
                client_message TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quotes_user_id ON quotes(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quotes_created_at ON quotes(created_at DESC)")

        master_hash = generate_password_hash(MASTER_PASSWORD)
        cur.execute(
            """
            INSERT INTO users (username, name, password_hash, is_master)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (username)
            DO UPDATE SET
                name = EXCLUDED.name,
                password_hash = EXCLUDED.password_hash,
                is_master = TRUE
            """,
            (MASTER_USERNAME, MASTER_NAME, master_hash),
        )
        conn.commit()


def _query_user_by_username(username: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, name, password_hash, is_master, created_at FROM users WHERE username = %s",
            (username.strip().lower(),),
        )
        return cur.fetchone()


def _query_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, name, password_hash, is_master, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        return cur.fetchone()


def _create_user(email: str, password: str) -> tuple[bool, str]:
    clean_email = email.strip().lower()

    if not clean_email:
        return False, "Informe o e-mail."
    if "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return False, "Informe um e-mail válido."
    if clean_email == MASTER_USERNAME:
        return False, "Este e-mail é reservado para o login master."
    if len(password) < 6:
        return False, "Senha precisa ter ao menos 6 caracteres."
    if _query_user_by_username(clean_email):
        return False, "E-mail já cadastrado."

    local_part = clean_email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
    display_name = " ".join(part for part in local_part.split() if part).title() or "Operador"

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, name, password_hash, is_master)
            VALUES (%s, %s, %s, FALSE)
            """,
            (clean_email, display_name, generate_password_hash(password)),
        )
        conn.commit()
    return True, "Cadastro realizado com sucesso."


def _insert_quote(
    user_id: int,
    result: Any,
    client_price_mode: str,
    client_price: Decimal,
    client_message: str,
) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO quotes (
                quote_code, user_id, origin, destination, volumes,
                weight_total_kg, cubage_total_m3, nf_value,
                base_cubage, base_weight, base_nf,
                average_simple, average_weighted,
                full_price, fair_price, max_discount_price,
                strategy_note, client_price_mode, client_price,
                client_message
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.quote_code,
                user_id,
                result.input_data.origin,
                result.input_data.destination,
                result.input_data.volumes,
                result.weight_total_kg,
                result.cubage_total_m3,
                result.input_data.nf_value,
                result.base_cubage,
                result.base_weight,
                result.base_nf,
                result.average_simple,
                result.average_weighted,
                result.full_price,
                result.fair_price,
                result.max_discount_price,
                result.strategy_note,
                client_price_mode,
                client_price,
                client_message,
            ),
        )
        conn.commit()


def _list_recent_quotes(current_user: dict[str, Any]) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        if current_user["is_master"]:
            cur.execute(
                """
                SELECT q.quote_code, q.origin, q.destination, q.client_price, q.client_price_mode, q.created_at,
                       u.name AS user_name, u.username AS user_username
                FROM quotes q
                INNER JOIN users u ON u.id = q.user_id
                ORDER BY q.id DESC
                LIMIT 30
                """
            )
        else:
            cur.execute(
                """
                SELECT q.quote_code, q.origin, q.destination, q.client_price, q.client_price_mode, q.created_at,
                       u.name AS user_name, u.username AS user_username
                FROM quotes q
                INNER JOIN users u ON u.id = q.user_id
                WHERE q.user_id = %s
                ORDER BY q.id DESC
                LIMIT 30
                """,
                (current_user["id"],),
            )
        return list(cur.fetchall())


def _get_quote_by_code(quote_code: str, current_user: dict[str, Any]) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        if current_user["is_master"]:
            cur.execute(
                """
                SELECT q.*, u.name AS user_name, u.username AS user_username
                FROM quotes q
                INNER JOIN users u ON u.id = q.user_id
                WHERE q.quote_code = %s
                """,
                (quote_code,),
            )
        else:
            cur.execute(
                """
                SELECT q.*, u.name AS user_name, u.username AS user_username
                FROM quotes q
                INNER JOIN users u ON u.id = q.user_id
                WHERE q.quote_code = %s AND q.user_id = %s
                """,
                (quote_code, current_user["id"]),
            )
        return cur.fetchone()


def _list_all_users() -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, name, is_master, created_at
            FROM users
            ORDER BY is_master DESC, username ASC
            """
        )
        return list(cur.fetchall())


def _user_profile_stats(user_id: int) -> dict[str, Any]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS quotes_count, MAX(created_at) AS last_quote_at
            FROM quotes
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone() or {}
        return {
            "quotes_count": int(row.get("quotes_count") or 0),
            "last_quote_at": row.get("last_quote_at"),
        }


def _format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "web" / "templates"),
        static_folder=str(PROJECT_ROOT / "web" / "static"),
    )
    app.config["SECRET_KEY"] = SECRET_KEY
    _init_db()

    @app.template_filter("brl")
    def _brl_filter(value: Any) -> str:
        return format_brl(Decimal(str(value)))

    @app.template_filter("display_date")
    def _display_date_filter(value: Any) -> str:
        return _format_dt(value)

    def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if g.current_user is None:
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapper

    def master_required(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if g.current_user is None:
                return redirect(url_for("login"))
            if not g.current_user["is_master"]:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    @app.before_request
    def _load_current_user() -> None:
        user_id = session.get("user_id")
        if not user_id:
            g.current_user = None
            return
        row = _query_user_by_id(int(user_id))
        if row is None:
            session.clear()
            g.current_user = None
            return
        g.current_user = {
            "id": row["id"],
            "username": row["username"],
            "name": row["name"],
            "is_master": bool(row["is_master"]),
            "created_at": row["created_at"],
        }

    @app.get("/")
    def home() -> Any:
        if g.current_user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if g.current_user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("email", "").strip().lower()
            if not username:
                username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            user = _query_user_by_username(username)
            if user is None or not check_password_hash(str(user["password_hash"]), password):
                flash("Usuário ou senha inválidos.", "error")
            else:
                session.clear()
                session["user_id"] = int(user["id"])
                flash("Login realizado com sucesso.", "success")
                return redirect(url_for("dashboard"))
        return render_template(
            "login.html",
            master_default_warning=(MASTER_USERNAME == "master" and MASTER_PASSWORD == "Master@123"),
        )

    @app.get("/forgot-password")
    def forgot_password() -> Any:
        return render_template("forgot_password.html")

    @app.route("/register", methods=["GET", "POST"])
    def register() -> Any:
        if request.method == "POST":
            email = request.form.get("email", "")
            password = request.form.get("password", "")
            ok, msg = _create_user(email, password)
            flash(msg, "success" if ok else "error")
            if ok:
                return redirect(url_for("login"))
        return render_template("register.html")

    @app.post("/logout")
    @login_required
    def logout() -> Any:
        session.clear()
        flash("Sessão encerrada.", "info")
        return redirect(url_for("login"))

    @app.get("/profile")
    @login_required
    def profile() -> Any:
        stats = _user_profile_stats(g.current_user["id"])
        return render_template("profile.html", stats=stats)

    @app.route("/dashboard", methods=["GET", "POST"])
    @login_required
    def dashboard() -> Any:
        if request.method == "POST":
            try:
                origin = request.form.get("origin", "").strip()
                destination = request.form.get("destination", "").strip()
                unit = request.form.get("unit", "m").strip().lower()
                if unit not in {"m", "cm", "m3"}:
                    raise ValueError("Unidade de dimensões inválida.")

                if unit == "m3":
                    provided_cubage = _to_decimal(request.form.get("cubage_total", "0"))
                    volumes = int(request.form.get("volumes_m3", "1"))
                    if provided_cubage <= 0:
                        raise ValueError("Cubagem total deve ser maior que zero.")
                    if volumes <= 0:
                        raise ValueError("Volumes totais devem ser maiores que zero.")
                else:
                    volumes, provided_cubage = _build_cubage_from_rows(unit, request.form)

                length = Decimal("1")
                width = Decimal("1")
                height = Decimal("1")
                nf_value = _to_decimal(request.form.get("nf_value", "0"))
                price_mode = request.form.get("price_mode", "justo").strip()
                weight_raw = request.form.get("weight", "").strip()
                total_weight = _to_decimal(weight_raw) if weight_raw else None

                data = QuoteInput(
                    origin=origin,
                    destination=destination,
                    volumes=volumes,
                    length_m=_to_meters(length, unit),
                    width_m=_to_meters(width, unit),
                    height_m=_to_meters(height, unit),
                    nf_value=nf_value,
                    provided_cubage_m3=provided_cubage,
                    total_weight_kg=total_weight,
                    cargo_type=None,
                )
                result = calculate_quote(data)
                client_price = _selected_price(result, price_mode)
                client_message = build_client_message(result, freight_value=client_price)
                _insert_quote(
                    user_id=g.current_user["id"],
                    result=result,
                    client_price_mode=price_mode,
                    client_price=client_price,
                    client_message=client_message,
                )
                flash(f"Cotação {result.quote_code} criada com sucesso.", "success")
                return redirect(url_for("quote_detail", quote_code=result.quote_code))
            except (ValueError, InvalidOperation) as exc:
                flash(str(exc), "error")

        recent_quotes = _list_recent_quotes(g.current_user)
        return render_template(
            "dashboard.html",
            cities=CITIES,
            price_modes=PRICE_MODES,
            recent_quotes=recent_quotes,
        )

    @app.get("/quotes/<quote_code>")
    @login_required
    def quote_detail(quote_code: str) -> Any:
        row = _get_quote_by_code(quote_code, g.current_user)
        if row is None:
            abort(404)
        internal_data = {
            "base_cubage": format_brl(Decimal(str(row["base_cubage"]))),
            "base_weight": format_brl(Decimal(str(row["base_weight"]))),
            "base_nf": format_brl(Decimal(str(row["base_nf"]))),
            "average_simple": format_brl(Decimal(str(row["average_simple"]))),
            "average_weighted": format_brl(Decimal(str(row["average_weighted"]))),
            "full_price": format_brl(Decimal(str(row["full_price"]))),
            "fair_price": format_brl(Decimal(str(row["fair_price"]))),
            "max_discount_price": format_brl(Decimal(str(row["max_discount_price"]))),
        }
        return render_template("quote_detail.html", quote=row, internal_data=internal_data)

    @app.route("/admin/users", methods=["GET", "POST"])
    @master_required
    def admin_users() -> Any:
        if request.method == "POST":
            email = request.form.get("email", "") or request.form.get("username", "")
            password = request.form.get("password", "")
            ok, msg = _create_user(email, password)
            flash(msg, "success" if ok else "error")
            if ok:
                return redirect(url_for("admin_users"))
        users = _list_all_users()
        return render_template("admin_users.html", users=users)

    @app.errorhandler(403)
    def forbidden(_: Any) -> Any:
        return (
            render_template(
                "error.html",
                title="Acesso negado",
                message="Você não tem permissão para acessar esta página.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(_: Any) -> Any:
        return (
            render_template(
                "error.html",
                title="Página não encontrada",
                message="O recurso solicitado não foi encontrado.",
            ),
            404,
        )

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "current_user": g.current_user,
            "master_username": MASTER_USERNAME,
            "price_mode_labels": PRICE_MODES,
        }

    return app

