import unittest

from app.supplies.parser import parse_supply_intent


class SupplyParserTest(unittest.TestCase):
    def test_example(self):
        intent = parse_supply_intent("Создай поставку в Москву:\nST-6  120 шт., по 30 в коробке")
        self.assertEqual(intent.destination, "Москву")
        self.assertEqual(intent.boxes, 4)

    def test_rejects_non_divisible_quantity(self):
        with self.assertRaisesRegex(ValueError, "не делится"):
            parse_supply_intent("Создай поставку в Москву:\nST-6  121 шт., по 30 в коробке")

