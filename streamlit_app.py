from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import sys

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from greew_quote.auth import (
    MASTER_PASSWORD,
    MASTER_USERNAME,
    authenticate,
    list_registered_users,
    register_user,
)
from greew_quote.engine import QuoteInput, build_client_message, calculate_quote, format_brl


CITIES = ["Sao Paulo", "Belem", "Manaus", "Macapa", "Boa Vista", "Fortaleza"]
PRICE_MODE_LABELS = {
    "cheio": "Valor cheio",
    "justo": "Valor justo (recomendado)",
    "desconto": "Desconto maximo",
}


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _to_meters(value: Decimal, unit: str) -> Decimal:
    if unit == "cm":
        return value / Decimal("100")
    return value


def _selected_price(result, mode: str) -> Decimal:
    if mode == "cheio":
        return result.full_price
    if mode == "desconto":
        return result.max_discount_price
    return result.fair_price


def _render_copy_button(text: str) -> None:
    safe_text = json.dumps(text)
    components.html(
        f"""
        <div style="display:flex;align-items:center;gap:12px;margin-top:6px;">
          <button id="copy-btn" style="
            border:none;
            border-radius:10px;
            padding:9px 14px;
            background:#16263f;
            color:#f2f6ff;
            font-weight:600;
            cursor:pointer;
          ">
            Copiar mensagem
          </button>
          <span id="copy-status" style="font-size:13px;color:#e8f2ff;"></span>
        </div>
        <script>
          const btn = document.getElementById("copy-btn");
          const status = document.getElementById("copy-status");
          const text = {safe_text};
          btn.addEventListener("click", async () => {{
            try {{
              await navigator.clipboard.writeText(text);
              status.innerText = "Mensagem copiada.";
            }} catch (err) {{
              status.innerText = "Copia automatica indisponivel neste navegador.";
            }}
          }});
        </script>
        """,
        height=56,
    )


def _ensure_session_state() -> None:
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None


def _set_logged_user(user) -> None:
    st.session_state.auth_user = {
        "username": user.username,
        "name": user.name,
        "is_master": user.is_master,
        "created_at": user.created_at,
    }


def _logout() -> None:
    st.session_state.auth_user = None
    st.rerun()


def _render_login_and_signup() -> bool:
    st.title("Sistema de Cotacao Greew")
    st.caption("Acesso restrito: login master e usuarios cadastrados.")

    tab_login, tab_signup = st.tabs(["Entrar", "Cadastrar usuario"])

    with tab_login:
        with st.form("login-form", clear_on_submit=False):
            st.subheader("Login")
            username = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            login_submit = st.form_submit_button("Entrar")

        if login_submit:
            user = authenticate(username=username, password=password)
            if user is None:
                st.error("Usuario ou senha invalidos.")
            else:
                _set_logged_user(user)
                st.success("Login realizado.")
                st.rerun()

        if MASTER_USERNAME == "master" and MASTER_PASSWORD == "Master@123":
            st.warning(
                "Credenciais master padrao ativas. Defina GREEW_MASTER_USER e "
                "GREEW_MASTER_PASSWORD para producao."
            )

    with tab_signup:
        with st.form("signup-form", clear_on_submit=True):
            st.subheader("Cadastro para cotacao")
            name = st.text_input("Nome completo")
            username = st.text_input("Novo usuario")
            password = st.text_input("Senha", type="password")
            confirm_password = st.text_input("Confirmar senha", type="password")
            signup_submit = st.form_submit_button("Cadastrar")

        if signup_submit:
            if password != confirm_password:
                st.error("As senhas nao conferem.")
            else:
                success, message = register_user(name=name, username=username, password=password)
                if success:
                    st.success(message)
                else:
                    st.error(message)

    return False


def _render_sidebar(current_user: dict) -> None:
    st.sidebar.title("Sessao")
    st.sidebar.write(f"Usuario: **{current_user['name']}**")
    st.sidebar.write(f"Login: `{current_user['username']}`")
    st.sidebar.write(f"Perfil: {'Master' if current_user['is_master'] else 'Operador'}")
    if st.sidebar.button("Sair", use_container_width=True):
        _logout()


def _render_master_panel() -> None:
    st.markdown("### Painel master")
    users = list_registered_users()
    st.info(f"Usuarios cadastrados: {len(users)}")
    if not users:
        st.caption("Nenhum usuario cadastrado ainda.")
        return

    rows = []
    for user in users:
        rows.append(
            {
                "Usuario": user.username,
                "Nome": user.name,
                "Criado em (UTC)": user.created_at or "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_quote_panel() -> None:
    st.markdown("### Cotacao")
    st.caption("Calculo interno completo + mensagem profissional pronta para o cliente")

    with st.form("quote-form", clear_on_submit=False):
        col_origin, col_destination = st.columns(2)
        origin = col_origin.selectbox("Origem", options=CITIES, index=0)
        destination = col_destination.selectbox("Destino", options=CITIES, index=1)

        col_volume, col_unit = st.columns([1, 1])
        volumes = col_volume.number_input("Volumes", min_value=1, step=1, value=1)
        unit = col_unit.radio("Unidade das dimensoes", options=["m", "cm"], horizontal=True)

        col_l, col_w, col_h = st.columns(3)
        length = col_l.number_input("Comprimento", min_value=0.01, step=0.01, value=1.20)
        width = col_w.number_input("Largura", min_value=0.01, step=0.01, value=0.80)
        height = col_h.number_input("Altura", min_value=0.01, step=0.01, value=1.00)

        inform_weight = st.checkbox("Peso total informado", value=True)
        weight = None
        cargo_type = None
        if inform_weight:
            weight = st.number_input("Peso total (kg)", min_value=0.01, step=1.0, value=200.0)
        else:
            cargo_type = st.selectbox(
                "Tipo de carga (estimativa de peso)",
                options=["Pecas industriais", "Maquinas", "Caixas pequenas", "Moveis"],
                index=0,
            )

        nf_value = st.number_input("Valor da NF (R$)", min_value=0.01, step=100.0, value=15000.0)
        price_mode = st.radio(
            "Preco para mensagem ao cliente",
            options=["justo", "cheio", "desconto"],
            format_func=lambda x: PRICE_MODE_LABELS[x],
            horizontal=True,
        )
        submit = st.form_submit_button("Gerar cotacao")

    if not submit:
        return

    data = QuoteInput(
        origin=origin,
        destination=destination,
        volumes=int(volumes),
        length_m=_to_meters(_to_decimal(length), unit),
        width_m=_to_meters(_to_decimal(width), unit),
        height_m=_to_meters(_to_decimal(height), unit),
        nf_value=_to_decimal(nf_value),
        total_weight_kg=_to_decimal(weight) if weight is not None else None,
        cargo_type=cargo_type,
    )

    try:
        result = calculate_quote(data)
    except ValueError as exc:
        st.error(str(exc))
        return

    client_price = _selected_price(result, price_mode)
    client_message = build_client_message(result, freight_value=client_price)

    st.markdown("### 1) DADOS DA CARGA")
    st.write(f"Origem: {result.input_data.origin}")
    st.write(f"Destino: {result.input_data.destination}")
    st.write(f"Volumes: {result.input_data.volumes}")
    st.write(f"Peso: {result.weight_total_kg} kg")
    st.write(f"Cubagem: {result.cubage_total_m3} m3")
    st.write(f"Valor da NF: {format_brl(result.input_data.nf_value)}")
    if result.weight_was_estimated and result.weight_estimation_note:
        st.info(result.weight_estimation_note)

    st.markdown("### 2) CALCULO INTERNO")
    col1, col2, col3 = st.columns(3)
    col1.metric("Base cubagem", format_brl(result.base_cubage))
    col2.metric("Base peso", format_brl(result.base_weight))
    col3.metric("Base NF", format_brl(result.base_nf))

    st.markdown("### 3) MEDIAS")
    col4, col5 = st.columns(2)
    col4.metric("Media simples", format_brl(result.average_simple))
    col5.metric("Media ponderada", format_brl(result.average_weighted))

    st.markdown("### 4) SUGESTAO DE PRECO")
    col6, col7, col8 = st.columns(3)
    col6.metric("Valor cheio", format_brl(result.full_price))
    col7.metric("Valor justo", format_brl(result.fair_price))
    col8.metric("Desconto maximo", format_brl(result.max_discount_price))
    st.caption(f"Analise: {result.strategy_note}")

    st.markdown("### 5) MENSAGEM PARA CLIENTE")
    st.text_area("Mensagem pronta", value=client_message, height=260)
    _render_copy_button(client_message)
    st.download_button(
        "Baixar mensagem (.txt)",
        data=client_message.encode("utf-8"),
        file_name=f"cotacao_{result.quote_code}.txt",
        mime="text/plain",
    )


st.set_page_config(page_title="Greew Cotacao", layout="wide")

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap');

      .stApp {
        background:
          radial-gradient(1200px 600px at -10% -10%, #d7e9ff 0%, transparent 45%),
          radial-gradient(800px 500px at 120% 0%, #f6efe3 0%, transparent 45%),
          linear-gradient(180deg, #f4f8ff 0%, #e9eef6 100%);
      }
      .block-container {
        max-width: 1120px;
        padding-top: 1.2rem;
      }
      h1, h2, h3 {
        font-family: "Space Grotesk", sans-serif !important;
        letter-spacing: -0.02em;
      }
      p, label, li, div {
        font-family: "Space Grotesk", sans-serif !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

_ensure_session_state()
current_user = st.session_state.auth_user
if not current_user:
    _render_login_and_signup()
    st.stop()

st.title("Sistema de Cotacao Greew")
_render_sidebar(current_user)

if current_user["is_master"]:
    _render_master_panel()
    st.divider()

_render_quote_panel()
