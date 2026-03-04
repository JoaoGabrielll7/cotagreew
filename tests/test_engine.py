from pathlib import Path
import sys
import unittest
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from greew_quote.engine import QuoteInput, calculate_quote, estimate_weight_kg, resolve_route


class QuoteEngineTests(unittest.TestCase):
    def test_reference_example_sao_paulo_belem(self) -> None:
        data = QuoteInput(
            origin="Sao Paulo",
            destination="Belem",
            volumes=3,
            length_m=Decimal("1.20"),
            width_m=Decimal("0.80"),
            height_m=Decimal("1.00"),
            total_weight_kg=Decimal("200"),
            nf_value=Decimal("15000"),
        )

        result = calculate_quote(data)

        self.assertEqual(result.cubage_total_m3, Decimal("2.88"))
        self.assertEqual(result.base_cubage, Decimal("864.00"))
        self.assertEqual(result.base_weight, Decimal("320.00"))
        self.assertEqual(result.base_nf, Decimal("1050.00"))
        self.assertEqual(result.average_simple, Decimal("744.67"))
        self.assertEqual(result.average_weighted, Decimal("793.80"))
        self.assertEqual(result.full_price, Decimal("1050.00"))
        self.assertEqual(result.fair_price, Decimal("793.80"))
        self.assertEqual(result.max_discount_price, Decimal("744.67"))

    def test_reverse_route_same_pricing(self) -> None:
        _, route_a = resolve_route("Sao Paulo", "Manaus")
        _, route_b = resolve_route("Manaus", "Sao Paulo")

        self.assertEqual(route_a, route_b)

    def test_weight_estimation(self) -> None:
        value, note = estimate_weight_kg("Maquinas")
        self.assertEqual(value, Decimal("500"))
        self.assertIn("500", note)

    def test_invalid_route_raises(self) -> None:
        data = QuoteInput(
            origin="Belem",
            destination="Manaus",
            volumes=1,
            length_m=Decimal("1"),
            width_m=Decimal("1"),
            height_m=Decimal("1"),
            total_weight_kg=Decimal("10"),
            nf_value=Decimal("1000"),
        )

        with self.assertRaises(ValueError):
            calculate_quote(data)

    def test_direct_cubage_input_in_m3(self) -> None:
        data = QuoteInput(
            origin="Sao Paulo",
            destination="Manaus",
            volumes=3,
            length_m=Decimal("0"),
            width_m=Decimal("0"),
            height_m=Decimal("0"),
            provided_cubage_m3=Decimal("4.00"),
            total_weight_kg=Decimal("100"),
            nf_value=Decimal("10000"),
        )

        result = calculate_quote(data)

        self.assertEqual(result.cubage_total_m3, Decimal("4.00"))
        self.assertEqual(result.base_cubage, Decimal("2000.00"))


if __name__ == "__main__":
    unittest.main()
