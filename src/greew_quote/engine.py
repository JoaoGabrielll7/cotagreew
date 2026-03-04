from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import random
import unicodedata


TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class RoutePricing:
    cubage_per_m3: Decimal
    weight_per_kg: Decimal
    nf_percent: Decimal


@dataclass
class QuoteInput:
    origin: str
    destination: str
    volumes: int
    length_m: Decimal
    width_m: Decimal
    height_m: Decimal
    nf_value: Decimal
    provided_cubage_m3: Decimal | None = None
    total_weight_kg: Decimal | None = None
    cargo_type: str | None = None


@dataclass
class QuoteResult:
    quote_code: str
    pricing_route: str
    input_data: QuoteInput
    cubage_total_m3: Decimal
    weight_total_kg: Decimal
    weight_was_estimated: bool
    weight_estimation_note: str | None
    base_cubage: Decimal
    base_weight: Decimal
    base_nf: Decimal
    average_simple: Decimal
    average_weighted: Decimal
    full_price: Decimal
    fair_price: Decimal
    max_discount_price: Decimal
    strategy_note: str


CITY_TO_UF = {
    "sao paulo": "SP",
    "belem": "PA",
    "manaus": "AM",
    "macapa": "AP",
    "boa vista": "RR",
    "fortaleza": "CE",
}

ROUTE_TABLE = {
    "belem": RoutePricing(Decimal("300"), Decimal("1.60"), Decimal("0.07")),
    "manaus": RoutePricing(Decimal("500"), Decimal("2.10"), Decimal("0.17")),
    "macapa": RoutePricing(Decimal("450"), Decimal("1.95"), Decimal("0.17")),
    "boa vista": RoutePricing(Decimal("600"), Decimal("2.50"), Decimal("0.18")),
    "fortaleza": RoutePricing(Decimal("500"), Decimal("2.10"), Decimal("0.17")),
}

WEIGHT_ESTIMATES = {
    "pecas industriais": (Decimal("80"), Decimal("200")),
    "maquinas": (Decimal("150"), Decimal("500")),
    "caixas pequenas": (Decimal("5"), Decimal("20")),
    "moveis": (Decimal("30"), Decimal("80")),
}


def _normalize_text(value: str) -> str:
    stripped = value.strip().lower()
    normalized = unicodedata.normalize("NFKD", stripped)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def parse_decimal(value: str) -> Decimal:
    cleaned = value.strip().replace("R$", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def format_brl(value: Decimal) -> str:
    rounded = _round_money(value)
    sign = "-" if rounded < 0 else ""
    abs_value = -rounded if rounded < 0 else rounded
    int_part, frac_part = f"{abs_value:.2f}".split(".")
    groups = []
    while int_part:
        groups.append(int_part[-3:])
        int_part = int_part[:-3]
    integer_formatted = ".".join(reversed(groups))
    return f"{sign}R$ {integer_formatted},{frac_part}"


def resolve_route(origin: str, destination: str) -> tuple[str, RoutePricing]:
    norm_origin = _normalize_text(origin)
    norm_dest = _normalize_text(destination)

    if norm_origin == norm_dest:
        raise ValueError("Origem e destino nao podem ser iguais.")

    if norm_origin == "sao paulo" and norm_dest in ROUTE_TABLE:
        return f"Sao Paulo <-> {destination.strip()}", ROUTE_TABLE[norm_dest]

    if norm_dest == "sao paulo" and norm_origin in ROUTE_TABLE:
        return f"Sao Paulo <-> {origin.strip()}", ROUTE_TABLE[norm_origin]

    raise ValueError(
        "Rota nao cadastrada. Use Sao Paulo <-> Belem/Manaus/Macapa/Boa Vista/Fortaleza."
    )


def estimate_weight_kg(cargo_type: str | None) -> tuple[Decimal, str]:
    if not cargo_type:
        return Decimal("100"), "Peso estimado padrao: 100 kg (tipo de carga nao informado)."

    normalized = _normalize_text(cargo_type)
    for key, (min_kg, max_kg) in WEIGHT_ESTIMATES.items():
        if key in normalized:
            return max_kg, f"Peso estimado com seguranca para '{cargo_type}': {max_kg} kg."

    return Decimal("100"), (
        f"Tipo de carga '{cargo_type}' fora da tabela. Peso estimado padrao: 100 kg."
    )


def generate_quote_code(destination: str) -> str:
    normalized_destination = _normalize_text(destination)
    uf = CITY_TO_UF.get(normalized_destination)
    if not uf:
        uf = "BR"
    number = random.SystemRandom().randint(10_000_000, 99_999_999)
    return f"{uf}{number}"


def _strategy_note(base_cubage: Decimal, base_weight: Decimal, base_nf: Decimal) -> str:
    dominant_value = max(base_cubage, base_weight, base_nf)
    second_value = sorted([base_cubage, base_weight, base_nf], reverse=True)[1]

    if dominant_value >= second_value * Decimal("1.80") and base_nf == dominant_value:
        return (
            "NF domina fortemente as bases. Usar media ponderada como recomendacao para "
            "evitar frete exagerado sem comprometer margem."
        )
    if dominant_value >= second_value * Decimal("1.40") and base_cubage == dominant_value:
        return (
            "Cubagem domina o custo. Manter negociacao acima da media simples para "
            "proteger margem operacional."
        )
    if dominant_value >= second_value * Decimal("1.40") and base_weight == dominant_value:
        return (
            "Peso domina o custo. Evitar desconto agressivo abaixo da media ponderada."
        )
    return "Bases equilibradas. Media ponderada segue como melhor referencia comercial."


def calculate_quote(data: QuoteInput) -> QuoteResult:
    if data.volumes <= 0:
        raise ValueError("A quantidade de volumes precisa ser maior que zero.")
    if data.nf_value <= 0:
        raise ValueError("Valor da NF precisa ser maior que zero.")

    pricing_route, route = resolve_route(data.origin, data.destination)

    if data.total_weight_kg is None or data.total_weight_kg <= 0:
        weight_total_kg, note = estimate_weight_kg(data.cargo_type)
        weight_estimated = True
    else:
        weight_total_kg = data.total_weight_kg
        note = None
        weight_estimated = False

    if data.provided_cubage_m3 is not None:
        if data.provided_cubage_m3 <= 0:
            raise ValueError("Cubagem informada precisa ser maior que zero.")
        cubage_total = data.provided_cubage_m3
    else:
        if data.length_m <= 0 or data.width_m <= 0 or data.height_m <= 0:
            raise ValueError("Dimensoes precisam ser maiores que zero.")
        cubage_unit = data.length_m * data.width_m * data.height_m
        cubage_total = cubage_unit * Decimal(data.volumes)

    base_cubage = _round_money(cubage_total * route.cubage_per_m3)
    base_weight = _round_money(weight_total_kg * route.weight_per_kg)
    base_nf = _round_money(data.nf_value * route.nf_percent)

    average_simple = _round_money((base_cubage + base_weight + base_nf) / Decimal("3"))
    average_weighted = _round_money(
        (base_nf * Decimal("0.50"))
        + (base_weight * Decimal("0.30"))
        + (base_cubage * Decimal("0.20"))
    )

    full_price = max(base_cubage, base_weight, base_nf)
    fair_price = average_weighted
    max_discount_price = average_simple

    strategy_note = _strategy_note(base_cubage, base_weight, base_nf)

    return QuoteResult(
        quote_code=generate_quote_code(data.destination),
        pricing_route=pricing_route,
        input_data=data,
        cubage_total_m3=_round_money(cubage_total),
        weight_total_kg=_round_money(weight_total_kg),
        weight_was_estimated=weight_estimated,
        weight_estimation_note=note,
        base_cubage=base_cubage,
        base_weight=base_weight,
        base_nf=base_nf,
        average_simple=average_simple,
        average_weighted=average_weighted,
        full_price=_round_money(full_price),
        fair_price=_round_money(fair_price),
        max_discount_price=_round_money(max_discount_price),
        strategy_note=strategy_note,
    )


def build_client_message(result: QuoteResult, freight_value: Decimal | None = None) -> str:
    selected = freight_value if freight_value is not None else result.fair_price

    return (
        f"Cotacao #{result.quote_code}\n\n"
        f"Origem: {result.input_data.origin}\n"
        f"Destino: {result.input_data.destination}\n\n"
        f"Volumes: {result.input_data.volumes}\n"
        f"Peso total: {result.weight_total_kg} kg\n"
        f"Cubagem: {result.cubage_total_m3} m3\n\n"
        f"Valor da NF: {format_brl(result.input_data.nf_value)}\n\n"
        f"Valor do frete: {format_brl(selected)}\n\n"
        "Prazo conforme programacao da rota."
    )


def build_internal_report(result: QuoteResult) -> str:
    weight_line = f"{result.weight_total_kg} kg"
    if result.weight_was_estimated:
        weight_line = f"{weight_line} (estimado)"

    lines = [
        "1) DADOS DA CARGA",
        f"Origem: {result.input_data.origin}",
        f"Destino: {result.input_data.destination}",
        f"Volumes: {result.input_data.volumes}",
        f"Peso: {weight_line}",
        f"Cubagem: {result.cubage_total_m3} m3",
        f"Valor da NF: {format_brl(result.input_data.nf_value)}",
        "",
        "2) CALCULO INTERNO",
        f"Base cubagem: {format_brl(result.base_cubage)}",
        f"Base peso: {format_brl(result.base_weight)}",
        f"Base NF: {format_brl(result.base_nf)}",
        "",
        "3) MEDIAS",
        f"Media simples: {format_brl(result.average_simple)}",
        f"Media ponderada: {format_brl(result.average_weighted)}",
        "",
        "4) SUGESTAO DE PRECO",
        f"Valor cheio: {format_brl(result.full_price)}",
        f"Valor justo (recomendado): {format_brl(result.fair_price)}",
        f"Desconto maximo: {format_brl(result.max_discount_price)}",
        "",
        "Analise inteligente:",
        result.strategy_note,
    ]

    if result.weight_estimation_note:
        lines.extend(["", f"Obs: {result.weight_estimation_note}"])

    lines.extend([
        "",
        "5) MENSAGEM PARA CLIENTE",
        build_client_message(result),
    ])

    return "\n".join(lines)
