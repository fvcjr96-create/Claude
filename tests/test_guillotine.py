"""Sanity checks on the survival model and the bid maths."""

from __future__ import annotations

import unittest

from guillotine.config import League, Player, Rival, Settings, load
from guillotine.engine import budget_value, build_plan, _max_bid, season_phase
from guillotine.lineup import add_value, optimize
from guillotine.market import market_for
from guillotine.sim import chop_probability, my_team_state, rival_states


def mk_roster(**over) -> list[Player]:
    base = [
        Player("QB1", "QB", 17.68), Player("RB1", "RB", 19.71),
        Player("RB2", "RB", 10.28), Player("WR1", "WR", 15.76),
        Player("WR2", "WR", 14.86), Player("TE1", "TE", 12.11),
        Player("WR3", "WR", 10.08), Player("WR4", "WR", 10.90),
    ]
    return base


def mk_league(projs, budget=1000.0, week=2) -> League:
    return League(
        week=week, my_team="Me", my_budget=budget, default_budget=1000.0,
        roster=mk_roster(),
        rivals=[Rival(f"R{i}", p, budget) for i, p in enumerate(projs)],
        settings=Settings(simulations=4000),
    )


FIELD = [116.41, 113.29, 111.59, 111.02, 110.23, 110.17, 107.29, 106.58,
         105.2, 103.8, 102.3, 100.5, 98.0, 94.5]


class TestLineup(unittest.TestCase):
    def test_optimal_lineup_matches_app_total(self):
        self.assertAlmostEqual(optimize(mk_roster()).points, 111.38, places=2)

    def test_add_replaces_worst_flex(self):
        delta, _, out = add_value(mk_roster(), Player("Nacua", "WR", 20.1))
        self.assertAlmostEqual(delta, 10.02, places=2)
        self.assertEqual(out.name, "WR3")

    def test_bench_only_add_is_worth_nothing(self):
        delta, _, out = add_value(mk_roster(), Player("Scrub", "WR", 4.0))
        self.assertEqual(delta, 0.0)
        self.assertIsNone(out)

    def test_flex_can_take_a_second_te(self):
        roster = mk_roster() + [Player("TE2", "TE", 30.0)]
        self.assertIn("TE2", [p.name for p in optimize(roster).starters])


class TestSurvival(unittest.TestCase):
    def test_chop_risk_falls_when_you_add_points(self):
        lg = mk_league(FIELD)
        rivals = rival_states(lg)
        weak = chop_probability(my_team_state(lg), rivals, lg.settings)
        strong = chop_probability(
            my_team_state(lg, [Player("Nacua", "WR", 20.1)]), rivals, lg.settings)
        self.assertLess(strong, weak)

    def test_worst_team_in_the_field_is_in_real_danger(self):
        lg = mk_league([p + 25 for p in FIELD])
        p = chop_probability(my_team_state(lg), rival_states(lg), lg.settings)
        self.assertGreater(p, 0.20)

    def test_best_team_in_the_field_is_nearly_safe(self):
        lg = mk_league([p - 30 for p in FIELD])
        p = chop_probability(my_team_state(lg), rival_states(lg), lg.settings)
        self.assertLess(p, 0.02)


class TestBidMaths(unittest.TestCase):
    def test_budget_curve_is_concave(self):
        first = budget_value(1000, 1000, 0.35) - budget_value(700, 1000, 0.35)
        last = budget_value(300, 1000, 0.35) - budget_value(0, 1000, 0.35)
        self.assertLess(first, last)

    def test_no_equity_gain_means_no_bid(self):
        lg = mk_league(FIELD)
        self.assertEqual(_max_bid(0.20, 0.20, 1000, lg), 0.0)

    def test_bigger_equity_gain_buys_a_bigger_bid(self):
        lg = mk_league(FIELD)
        small = _max_bid(0.205, 0.200, 1000, lg)
        big = _max_bid(0.260, 0.200, 1000, lg)
        self.assertLess(small, big)

    def test_max_bid_respects_the_reserve(self):
        lg = mk_league(FIELD)
        self.assertLessEqual(_max_bid(0.90, 0.01, 1000, lg), 1000 - lg.settings.min_reserve)

    def test_market_price_rises_with_player_quality(self):
        lg = mk_league(FIELD)
        cheap = market_for(Player("Scrub", "WR", 9.5), lg).price_for(0.5, 1000)
        dear = market_for(Player("Nacua", "WR", 20.1, rostered_pct=99.8), lg).price_for(0.5, 1000)
        self.assertLess(cheap, dear)

    def test_p_win_is_monotonic_in_the_bid(self):
        m = market_for(Player("Nacua", "WR", 20.1, rostered_pct=99.8), mk_league(FIELD))
        probs = [m.p_win(b) for b in range(0, 1000, 50)]
        self.assertEqual(probs, sorted(probs))

    def test_a_broke_field_is_cheap_to_outbid(self):
        rich = market_for(Player("Nacua", "WR", 20.1), mk_league(FIELD, budget=1000))
        poor = market_for(Player("Nacua", "WR", 20.1), mk_league(FIELD, budget=120))
        self.assertLess(poor.price_for(0.5, 1000), rich.price_for(0.5, 1000))


class TestPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(load("data/week02.json"))

    def test_best_player_available_is_the_primary_target(self):
        self.assertEqual(self.plan.primary.player.name, "Puka Nacua")

    def test_a_player_who_cannot_start_gets_no_bid(self):
        goff = [c for c in self.plan.candidates if c.player.name == "Jared Goff"][0]
        self.assertEqual(goff.lineup_delta, 0.0)
        self.assertEqual(goff.recommended_bid, 0.0)

    def test_recommended_bid_never_exceeds_the_ceiling(self):
        for c in self.plan.candidates:
            self.assertLessEqual(c.recommended_bid, c.max_bid + 1e-6)

    def test_every_add_lowers_chop_risk_or_does_nothing(self):
        for c in self.plan.candidates:
            self.assertLessEqual(c.p_chop_with, self.plan.baseline_chop + 1e-9)

    def test_phase_hardens_as_the_field_shrinks(self):
        lg = load("data/week02.json")
        self.assertEqual(season_phase(lg)[0], "LAND GRAB")
        lg.rivals = lg.rivals[:7]
        self.assertEqual(season_phase(lg)[0], "SQUEEZE")
        lg.rivals = lg.rivals[:5]
        self.assertEqual(season_phase(lg)[0], "KNIFE FIGHT")
        lg.rivals = lg.rivals[:3]
        self.assertEqual(season_phase(lg)[0], "ENDGAME")


class TestConfig(unittest.TestCase):
    def test_week02_snapshot_loads_and_flags_its_gaps(self):
        lg = load("data/week02.json")
        self.assertEqual(lg.teams_left, 15)
        self.assertEqual(lg.weeks_left, 16)
        warns = " ".join(lg.validate())
        self.assertIn("bench", warns)
        self.assertIn("estimates", warns)

    def test_unknown_settings_key_is_rejected(self):
        with self.assertRaises(ValueError):
            Settings.from_dict({"budget_alfa": 0.4})


if __name__ == "__main__":
    unittest.main()
