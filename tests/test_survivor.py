"""Correctness checks for the survivor planner."""

from __future__ import annotations

import itertools
import random
import unittest

from survivor.assign import BLOCKED, solve, total_cost
from survivor.data import Board, Game, TEAMS, Week, load
from survivor.model import prob_from_spread, spread_from_prob
from survivor.plan import (next_week_options, opponent_concentration, optimize,
                           optimize_capped, team_leverage)
from survivor.ratings import fit


class TestAssignment(unittest.TestCase):
    def test_matches_brute_force_on_random_matrices(self):
        rng = random.Random(11)
        for _ in range(150):
            n = rng.randint(1, 6)
            m = n + rng.randint(0, 3)
            c = [[rng.random() for _ in range(m)] for _ in range(n)]
            got = total_cost(c, solve(c))
            want = min(sum(c[i][j] for i, j in enumerate(p))
                       for p in itertools.permutations(range(m), n))
            self.assertAlmostEqual(got, want, places=9)

    def test_avoids_the_greedy_trap(self):
        # Row 0 prefers column 0, but row 1 can ONLY use column 0.
        c = [[1.0, 2.0], [1.0, BLOCKED]]
        self.assertEqual(solve(c), [1, 0])

    def test_every_row_gets_a_distinct_column(self):
        rng = random.Random(3)
        c = [[rng.random() for _ in range(9)] for _ in range(7)]
        a = solve(c)
        self.assertEqual(len(set(a)), 7)

    def test_rejects_more_rows_than_columns(self):
        with self.assertRaises(ValueError):
            solve([[1.0], [2.0]])


class TestModel(unittest.TestCase):
    def test_calibrated_against_sourced_week2_lines(self):
        # Sourced: SF -13.5 -> 85%, BAL -8.5 -> 74%, LAC -6.5 -> 69%.
        self.assertAlmostEqual(prob_from_spread(13.5), 0.85, places=2)
        self.assertAlmostEqual(prob_from_spread(8.5), 0.74, places=2)
        self.assertAlmostEqual(prob_from_spread(6.5), 0.69, places=2)

    def test_pickem_is_a_coin_flip(self):
        self.assertAlmostEqual(prob_from_spread(0.0), 0.5, places=9)

    def test_spread_and_probability_round_trip(self):
        for s in (-10.0, -3.0, 0.0, 2.5, 7.0, 14.0):
            self.assertAlmostEqual(spread_from_prob(prob_from_spread(s)), s, places=3)

    def test_underdog_and_favourite_probabilities_sum_to_one(self):
        self.assertAlmostEqual(prob_from_spread(7.0) + prob_from_spread(-7.0), 1.0, places=9)


def synthetic_board(seed: int = 5, weeks: int = 6, used=None) -> Board:
    rng = random.Random(seed)
    ratings = {t: rng.gauss(0, 5.5) for t in TEAMS}
    wks = []
    for w in range(1, weeks + 1):
        pool = TEAMS[:]
        rng.shuffle(pool)
        games = [
            Game(w, pool[i + 1], pool[i],
                 home_spread=ratings[pool[i]] - ratings[pool[i + 1]] + 1.8)
            for i in range(0, 32, 2)
        ]
        wks.append(Week(w, games, verified=True))
    return Board(2026, wks, used=used or {})


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.board = synthetic_board(used={1: "PIT"})

    def test_never_reuses_a_team(self):
        picks = [p.team for p in optimize(self.board).picks]
        self.assertEqual(len(picks), len(set(picks)))

    def test_never_picks_an_already_used_team(self):
        self.assertNotIn("PIT", [p.team for p in optimize(self.board).picks])

    def test_plans_only_future_weeks(self):
        self.assertEqual([p.week for p in optimize(self.board).picks], [2, 3, 4, 5, 6])

    def test_beats_the_greedy_week_by_week_strategy(self):
        plan = optimize(self.board)
        greedy, used, survival = [], {"PIT"}, 1.0
        for wk in self.board.future_weeks():
            best, bp = None, -1.0
            for t in wk.teams_playing() - used:
                p = wk.game_for(t).prob_for(t)
                if p > bp:
                    best, bp = t, p
            used.add(best)
            survival *= bp
        self.assertGreaterEqual(plan.survival, survival)

    def test_survival_is_the_product_of_the_picks(self):
        plan = optimize(self.board)
        prod = 1.0
        for p in plan.picks:
            prod *= p.prob
        self.assertAlmostEqual(plan.survival, prod, places=9)

    def test_forcing_a_pick_is_respected(self):
        plan = optimize(self.board, force={2: "DAL"})
        self.assertEqual(plan.picks[0].team, "DAL")

    def test_forcing_a_pick_cannot_beat_the_free_optimum(self):
        best = optimize(self.board).survival
        legal = sorted(self.board.future_weeks()[0].teams_playing() - self.board.used_teams)
        for team in legal[:8]:
            self.assertLessEqual(optimize(self.board, force={2: team}).survival, best + 1e-12)

    def test_forcing_an_already_used_team_is_refused(self):
        with self.assertRaises(ValueError):
            optimize(self.board, force={2: "PIT"})

    def test_banning_a_team_never_helps(self):
        best = optimize(self.board).survival
        self.assertLessEqual(optimize(self.board, ban={"KC"}).survival, best + 1e-12)

    def test_leverage_is_never_negative(self):
        for _team, v in team_leverage(self.board):
            self.assertGreaterEqual(v, -1e-12)

    def test_next_week_options_are_ranked_by_season_survival(self):
        opts = next_week_options(self.board)
        self.assertEqual([o[2] for o in opts], sorted([o[2] for o in opts], reverse=True))

    def test_the_top_option_matches_the_full_plan(self):
        self.assertEqual(next_week_options(self.board)[0][0], optimize(self.board).picks[0].team)

    def test_bye_weeks_are_never_picked(self):
        board = synthetic_board(weeks=3)
        board.weeks[1].games = board.weeks[1].games[:8]   # 16 teams on bye
        playing = board.weeks[1].teams_playing()
        pick = [p for p in optimize(board).picks if p.week == 2][0]
        self.assertIn(pick.team, playing)

    def test_contrarian_mode_shifts_off_the_chalk(self):
        board = synthetic_board(weeks=4, used={1: "PIT"})
        chalk = optimize(board).picks[0].team
        board.weeks[1].popularity = {chalk: 0.9}
        self.assertNotEqual(optimize(board, contrarian=5.0).picks[0].team, chalk)


class TestConcentrationCap(unittest.TestCase):
    def setUp(self):
        self.board = load("data/survivor_2026.json")

    def test_cap_is_respected(self):
        plan = optimize_capped(self.board, max_vs=3)
        self.assertLessEqual(max(c for _o, c in opponent_concentration(plan)), 3)

    def test_cap_costs_survival_but_not_much(self):
        free = optimize(self.board).survival
        capped = optimize_capped(self.board, max_vs=3).survival
        self.assertLessEqual(capped, free + 1e-12)
        self.assertGreater(capped, free * 0.5)

    def test_capped_plan_still_uses_each_team_once(self):
        picks = [p.team for p in optimize_capped(self.board, max_vs=3).picks]
        self.assertEqual(len(picks), len(set(picks)))


class TestRidgeValidation(unittest.TestCase):
    """The ridge default is an empirical claim; keep it honest."""

    def _holdout(self):
        import copy as _copy
        from survivor.model import spread_from_prob
        board = load("data/survivor_2026.json")
        priced = [w.number for w in board.weeks
                  if any(g.home_prob is not None or g.home_spread is not None
                         for g in w.games)]
        hold = priced[-1]
        truth = [(g.home, g.away,
                  spread_from_prob(g.home_prob) if g.home_prob is not None else g.home_spread)
                 for w in board.weeks if w.number == hold for g in w.games
                 if g.home_prob is not None or g.home_spread is not None]
        train = _copy.deepcopy(board)
        for w in train.weeks:
            if w.number not in priced[:-1]:
                for g in w.games:
                    g.home_spread = g.home_prob = None
        return train, truth

    def _mae(self, ridge):
        train, truth = self._holdout()
        r = fit(train, ridge=ridge)
        return sum(abs(r.spread(h, a) - s) for h, a, s in truth) / len(truth)

    def test_default_ridge_beats_a_home_field_only_baseline(self):
        from survivor.model import HOME_FIELD
        from survivor.ratings import RIDGE
        _train, truth = self._holdout()
        base = sum(abs(HOME_FIELD - s) for _h, _a, s in truth) / len(truth)
        self.assertLess(self._mae(RIDGE), base * 0.6)

    def test_default_ridge_beats_over_and_under_shrinking(self):
        from survivor.ratings import RIDGE
        self.assertLess(self._mae(RIDGE), self._mae(0.01))
        self.assertLess(self._mae(RIDGE), self._mae(5.0))


class TestRatings(unittest.TestCase):
    def test_recovers_known_ratings_from_spreads(self):
        rng = random.Random(7)
        true = {t: rng.gauss(0, 5) for t in TEAMS}
        wks = []
        for w in range(1, 10):
            pool = TEAMS[:]
            rng.shuffle(pool)
            wks.append(Week(w, [
                Game(w, pool[i + 1], pool[i],
                     home_spread=true[pool[i]] - true[pool[i + 1]] + 1.8)
                for i in range(0, 32, 2)
            ], verified=True))
        r = fit(Board(2026, wks), ridge=0.5)
        centred = {t: v - sum(true.values()) / 32 for t, v in true.items()}
        err = max(abs(r.values[t] - centred[t]) for t in TEAMS)
        self.assertLess(err, 1.0)

    def test_ratings_are_centred_on_zero(self):
        r = fit(synthetic_board(weeks=8))
        self.assertAlmostEqual(sum(r.values.values()) / len(r.values), 0.0, places=9)


class TestRealBoard(unittest.TestCase):
    def setUp(self):
        self.board = load("data/survivor_2026.json")

    def test_loads_with_the_steelers_already_used(self):
        self.assertEqual(self.board.used, {1: "PIT"})
        self.assertIn("PIT", self.board.used_teams)

    def test_has_the_whole_272_game_season(self):
        self.assertEqual(len(self.board.weeks), 18)
        self.assertEqual(sum(len(w.games) for w in self.board.weeks), 272)

    def test_market_priced_weeks_are_verified(self):
        self.assertGreaterEqual(self.board.verified_through(), 2)

    def test_every_team_plays_every_week_it_is_not_on_bye(self):
        for w in self.board.weeks:
            teams = [t for g in w.games for t in (g.home, g.away)]
            self.assertEqual(len(teams), len(set(teams)), f"week {w.number} double-books a team")

    def test_each_team_plays_seventeen_games(self):
        from collections import Counter
        c = Counter(t for w in self.board.weeks for g in w.games for t in (g.home, g.away))
        self.assertEqual(set(c.values()), {17})

    def test_market_prices_match_independently_sourced_numbers(self):
        wk2 = [w for w in self.board.weeks if w.number == 2][0]
        # Sourced from Week 2 writeups: SF ~85%, BAL ~74%.
        self.assertAlmostEqual(wk2.game_for("SF").prob_for("SF"), 0.85, delta=0.03)
        self.assertAlmostEqual(wk2.game_for("BAL").prob_for("BAL"), 0.74, delta=0.03)

    def test_finished_games_are_not_pickable(self):
        wk2 = [w for w in self.board.weeks if w.number == 2][0]
        self.assertTrue(any(g.played for g in wk2.games))
        for g in wk2.games:
            if g.played:
                self.assertNotIn(g.home, wk2.teams_playing())
                self.assertNotIn(g.away, wk2.teams_playing())

    def test_the_steelers_are_not_offered_again(self):
        self.assertNotIn("PIT", [o[0] for o in next_week_options(self.board)])


if __name__ == "__main__":
    unittest.main()
