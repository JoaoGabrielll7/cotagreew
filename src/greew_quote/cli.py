from __future__ import annotations

import argparse
from decimal import Decimal

from .engine import (
    QuoteInput,
    build_client_message,
    build_internal_report,
    calculate_quote,
    format_brl,
    parse_decimal,
)


def _to_meters(value: Decimal, unit: str) -> Decimal:
    if unit == "cm":
        return value / Decimal("100")
    return value


def _read_decimal(prompt: str) -> Decimal:
    raw = input(prompt).strip()
    return parse_decimal(raw)


def _read_optional_decimal(prompt: str) -> Decimal | None:
    raw = input(prompt).strip()
    if not raw:
        return None
    return parse_decimal(raw)


def _read_int(prompt: str) -> int:
    raw = input(prompt).strip()
    return int(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema de Cotacao Greew Transportadora"
    )
    parser.add_argument("--origem", help="Cidade de origem")
    parser.add_argument("--destino", help="Cidade de destino")
    parser.add_argument("--volumes", type=int, help="Quantidade de volumes")
    parser.add_argument("--comprimento", help="Comprimento unitario")
    parser.add_argument("--largura", help="Largura unitario")
    parser.add_argument("--altura", help="Altura unitario")
    parser.add_argument("--unidade", choices=["m", "cm"], default="m")
    parser.add_argument("--peso", help="Peso total em kg (opcional)")
    parser.add_argument("--tipo-carga", help="Tipo de carga para estimativa")
    parser.add_argument("--nf", help="Valor da nota fiscal")
    parser.add_argument(
        "--preco-cliente",
        choices=["cheio", "justo", "desconto"],
        default="justo",
        help="Preco usado na mensagem do cliente",
    )
    return parser.parse_args()


def _collect_interactive(args: argparse.Namespace) -> argparse.Namespace:
    if args.origem:
        return args

    print("Sistema de Cotacao Greew")
    print("Preencha os dados abaixo:\n")

    args.origem = input("Origem: ").strip()
    args.destino = input("Destino: ").strip()
    args.volumes = _read_int("Volumes (quantidade): ")

    unidade = input("Dimensoes em m ou cm? [m/cm] (padrao m): ").strip().lower()
    args.unidade = unidade if unidade in {"m", "cm"} else "m"

    args.comprimento = str(_read_decimal("Comprimento unitario: "))
    args.largura = str(_read_decimal("Largura unitario: "))
    args.altura = str(_read_decimal("Altura unitario: "))

    peso = _read_optional_decimal("Peso total em kg (opcional): ")
    args.peso = str(peso) if peso is not None else None

    args.tipo_carga = input("Tipo de carga (opcional): ").strip() or None
    args.nf = str(_read_decimal("Valor da NF: "))
    return args


def _choose_client_price(preco_cliente: str, full: Decimal, fair: Decimal, discount: Decimal) -> Decimal:
    if preco_cliente == "cheio":
        return full
    if preco_cliente == "desconto":
        return discount
    return fair


def run() -> None:
    args = _collect_interactive(parse_args())

    if not all([args.origem, args.destino, args.volumes, args.comprimento, args.largura, args.altura, args.nf]):
        raise SystemExit("Dados insuficientes para cotacao. Informe origem, destino, volumes, dimensoes e NF.")

    comprimento = _to_meters(parse_decimal(str(args.comprimento)), args.unidade)
    largura = _to_meters(parse_decimal(str(args.largura)), args.unidade)
    altura = _to_meters(parse_decimal(str(args.altura)), args.unidade)

    data = QuoteInput(
        origin=str(args.origem),
        destination=str(args.destino),
        volumes=int(args.volumes),
        length_m=comprimento,
        width_m=largura,
        height_m=altura,
        nf_value=parse_decimal(str(args.nf)),
        total_weight_kg=parse_decimal(str(args.peso)) if args.peso else None,
        cargo_type=args.tipo_carga,
    )

    result = calculate_quote(data)
    print()
    print(build_internal_report(result))

    client_price = _choose_client_price(
        args.preco_cliente,
        result.full_price,
        result.fair_price,
        result.max_discount_price,
    )

    print("\nResumo comercial:")
    print(f"- Codigo da cotacao: {result.quote_code}")
    print(f"- Preco selecionado para cliente ({args.preco_cliente}): {format_brl(client_price)}")
    print("\nMensagem pronta para copiar:")
    print(build_client_message(result, freight_value=client_price))


if __name__ == "__main__":
    run()
