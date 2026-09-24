"""Tests for the pure financial calculations."""
import datetime as dt
from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.choices import InterestMode, PaymentFrequency
from apps.core.money import money, split_into_installments
from apps.loans.calculations import (
    build_schedule,
    calculate_interest,
    calculate_total_payable,
    due_dates,
    simulate,
)

FLAT = InterestMode.FLAT_ON_PRINCIPAL


class InterestPerThousandTests(SimpleTestCase):
    """The commercial rule: 400 MXN of interest per 1,000 MXN lent."""

    def test_commercial_rule_table(self):
        cases = [
            ("1000", "400.00", "1400.00"),
            ("2000", "800.00", "2800.00"),
            ("3000", "1200.00", "4200.00"),
            ("5000", "2000.00", "7000.00"),
            ("10000", "4000.00", "14000.00"),
        ]
        for principal, expected_interest, expected_total in cases:
            with self.subTest(principal=principal):
                interest = calculate_interest(Decimal(principal), FLAT, Decimal("0.40"))
                self.assertEqual(interest, Decimal(expected_interest))
                self.assertEqual(
                    calculate_total_payable(Decimal(principal), interest),
                    Decimal(expected_total),
                )

    def test_non_divisible_principal_rounds_to_cents(self):
        interest = calculate_interest(Decimal("1333.33"), FLAT, Decimal("0.40"))
        self.assertEqual(interest, Decimal("533.33"))

    def test_no_interest(self):
        self.assertEqual(
            calculate_interest(Decimal("1000"), InterestMode.NO_INTEREST, Decimal("0.40")),
            Decimal("0.00"),
        )

    def test_simple_interest_per_period_is_not_compounded(self):
        # 1,000 at 5% per period for 4 periods = 200, NOT 215.51 (compounded).
        interest = calculate_interest(
            Decimal("1000"), InterestMode.SIMPLE_PER_PERIOD, Decimal("0.05"), 4)
        self.assertEqual(interest, Decimal("200.00"))

    def test_invalid_principal(self):
        with self.assertRaises(ValueError):
            calculate_interest(Decimal("0"), FLAT, Decimal("0.40"))

    def test_negative_rate(self):
        with self.assertRaises(ValueError):
            calculate_interest(Decimal("1000"), FLAT, Decimal("-0.1"))


class InstallmentRoundingTests(SimpleTestCase):
    def test_installments_add_up_to_the_total(self):
        for total, count in [("1400", 4), ("1000", 3), ("999.99", 7), ("100", 6)]:
            with self.subTest(total=total, count=count):
                installments = split_into_installments(Decimal(total), count)
                self.assertEqual(len(installments), count)
                self.assertEqual(sum(installments), money(Decimal(total)))

    def test_last_installment_absorbs_the_difference(self):
        installments = split_into_installments(Decimal("1000"), 3)
        self.assertEqual(installments,
                         [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")])

    def test_single_installment(self):
        self.assertEqual(split_into_installments(Decimal("1400"), 1),
                         [Decimal("1400.00")])

    def test_zero_installments_is_an_error(self):
        with self.assertRaises(ValueError):
            split_into_installments(Decimal("1000"), 0)


class ScheduleTests(SimpleTestCase):
    def setUp(self):
        self.start = dt.date(2026, 1, 5)

    def test_four_weekly_installments(self):
        schedule = build_schedule(
            Decimal("1000"), Decimal("400"), 4, self.start, PaymentFrequency.WEEKLY)
        self.assertEqual(len(schedule), 4)
        for row in schedule:
            self.assertEqual(row["scheduled_amount"], Decimal("350.00"))
        self.assertEqual(
            [row["due_date"] for row in schedule],
            [dt.date(2026, 1, 5), dt.date(2026, 1, 12),
             dt.date(2026, 1, 19), dt.date(2026, 1, 26)],
        )

    def test_schedule_totals_match(self):
        schedule = build_schedule(
            Decimal("1333.33"), Decimal("533.33"), 7, self.start, PaymentFrequency.DAILY)
        self.assertEqual(sum(row["scheduled_principal"] for row in schedule),
                         Decimal("1333.33"))
        self.assertEqual(sum(row["scheduled_interest"] for row in schedule),
                         Decimal("533.33"))
        self.assertEqual(sum(row["scheduled_amount"] for row in schedule),
                         Decimal("1866.66"))

    def test_frequencies(self):
        cases = {
            PaymentFrequency.DAILY: dt.date(2026, 1, 6),
            PaymentFrequency.WEEKLY: dt.date(2026, 1, 12),
            PaymentFrequency.BIWEEKLY: dt.date(2026, 1, 20),
            PaymentFrequency.MONTHLY: dt.date(2026, 2, 5),
        }
        for frequency, second_date in cases.items():
            with self.subTest(frequency=frequency):
                dates = due_dates(self.start, frequency, 2)
                self.assertEqual(dates[1], second_date)

    def test_monthly_respects_end_of_month(self):
        dates = due_dates(dt.date(2026, 1, 31), PaymentFrequency.MONTHLY, 3)
        self.assertEqual(dates[1], dt.date(2026, 2, 28))
        self.assertEqual(dates[2], dt.date(2026, 3, 31))

    def test_custom_frequency_requires_days(self):
        with self.assertRaises(ValueError):
            due_dates(self.start, PaymentFrequency.CUSTOM, 3)
        dates = due_dates(self.start, PaymentFrequency.CUSTOM, 3, custom_days=10)
        self.assertEqual(dates[2], dt.date(2026, 1, 25))

    def test_full_simulation(self):
        result = simulate(Decimal("5000"), FLAT, Decimal("0.40"), 10,
                          self.start, PaymentFrequency.WEEKLY)
        self.assertEqual(result["total_interest"], Decimal("2000.00"))
        self.assertEqual(result["total_payable"], Decimal("7000.00"))
        self.assertEqual(result["installment_amount"], Decimal("700.00"))
        self.assertEqual(result["final_due_date"], dt.date(2026, 3, 9))
