"""Correctness checks for the survivor planner."""

from __future__ import annotations

import itertools
import random
import unittest

from survivor.assign import BLOCKED, solve, total_cost
from survivor.data import Board, Game, TEAMS, Week, load
from survivor.model import prob_from_spread, spread_from_prob
from survivor import cost as cost_mod
from survivor.pipeline import build_ratings
from survivor.wintotals import expected_wins, solve as solve_totals
from survivor.plan import (next_week_options, opponent_concentration, optimize,
                           optimize_capped, team_leverage)
from survivor.ratings import fit, fill
from survivor.simulate import simulate_adaptive, simulate_static


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
    return Board(2026, wks, used={w: [t] for w, t in (used or {}).items()})


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


class TestSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load("data/survivor_2026.json")
        fill(cls.board, fit(cls.board))
        cls.plan = optimize(cls.board)

    def test_without_model_error_it_reproduces_the_analytic_product(self):
        r = simulate_static(self.board, self.plan, sims=60000,
                            model_error=False, seed=1)
        self.assertAlmostEqual(r.overall, self.plan.survival, delta=4 * r.se)

    def test_per_week_survival_tracks_the_running_product(self):
        """Survival ticks once per WEEK -- a double week only after both land."""
        r = simulate_static(self.board, self.plan, sims=60000,
                            model_error=False, seed=1)
        run = 1.0
        for wk_num, picks in sorted(self.plan.by_week().items())[:6]:
            for p in picks:
                run *= p.prob
            self.assertAlmostEqual(r.survival_by_week[wk_num], run, delta=0.015)

    def test_survival_never_exceeds_one(self):
        r = simulate_static(self.board, self.plan, sims=20000, seed=1)
        for v in r.survival_by_week.values():
            self.assertLessEqual(v, 1.0)

    def test_survival_only_falls_as_weeks_pass(self):
        r = simulate_static(self.board, self.plan, sims=20000, seed=1)
        curve = [r.survival_by_week[p.week] for p in self.plan.picks]
        self.assertEqual(curve, sorted(curve, reverse=True))

    def test_standard_error_shrinks_with_more_simulations(self):
        small = simulate_static(self.board, self.plan, sims=5000, seed=1)
        big = simulate_static(self.board, self.plan, sims=50000, seed=1)
        self.assertLess(big.se, small.se)

    def test_more_drift_never_makes_a_plan_look_better_than_certainty(self):
        certain = simulate_static(self.board, self.plan, sims=40000,
                                  model_error=False, seed=1)
        drifty = simulate_static(self.board, self.plan, sims=40000,
                                 seed=1, drift=1.2)
        self.assertLess(drifty.overall, certain.overall + 4 * certain.se)

    def test_replanning_without_new_information_changes_nothing(self):
        """Adaptive only helps because lines improve, not because it adapts."""
        import copy
        state = copy.deepcopy(self.board)
        walked = []
        for _ in range(len(self.plan.picks)):
            pl = optimize(state)
            if not pl.picks:
                break
            walked.extend(p.team for p in pl.picks if p.week == pl.picks[0].week)
            state.used[pl.picks[0].week] = [p.team for p in pl.picks
                                        if p.week == pl.picks[0].week]
        # Compare week by week: order within a double week is not meaningful.
        walked_by_week, i = {}, 0
        for wk_num, picks in sorted(self.plan.by_week().items()):
            walked_by_week[wk_num] = set(walked[i:i + len(picks)])
            i += len(picks)
        self.assertEqual(walked_by_week,
                         {w: {p.team for p in ps}
                          for w, ps in self.plan.by_week().items()})

    def test_adaptive_simulation_agrees_with_static(self):
        a = simulate_static(self.board, self.plan, sims=4000, seed=5)
        b = simulate_adaptive(self.board, sims=400, seed=5)
        self.assertAlmostEqual(a.mean_weeks_survived, b.mean_weeks_survived, delta=0.5)


class TestOpportunityCost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load("data/survivor_2026.json")
        build_ratings(cls.board, "data/prior_2026.json", "data/win_totals_2026.json")
        cls.costs = cost_mod.build(cls.board)

    def test_every_remaining_team_is_priced(self):
        expected = {t for w in self.board.future_weeks() for t in w.teams_playing()}
        expected -= self.board.used_teams
        self.assertEqual({t.team for t in self.costs.teams}, expected)

    def test_no_pinning_ever_beats_the_unconstrained_optimum(self):
        for tc in self.costs.teams:
            for _wk, surv in tc.by_week.items():
                self.assertLessEqual(surv, self.costs.optimum + 1e-12)

    def test_best_week_really_is_the_best_week(self):
        for tc in self.costs.teams:
            self.assertEqual(tc.best_survival, max(tc.by_week.values()))
            self.assertEqual(tc.by_week[tc.best_week], tc.best_survival)

    def test_opportunity_cost_is_never_negative(self):
        for tc in self.costs.teams:
            if tc.earliness_cost is not None:
                self.assertGreaterEqual(tc.earliness_cost, -1e-12)

    def test_a_team_is_never_priced_on_its_bye(self):
        for tc in self.costs.teams:
            for wk_num in tc.by_week:
                wk = next(w for w in self.board.weeks if w.number == wk_num)
                self.assertIn(tc.team, wk.teams_playing())

    def test_some_team_is_free_to_use_now(self):
        """If nothing were free the optimum itself would be unreachable."""
        cheapest = self.costs.cheapest_now(1)[0]
        self.assertAlmostEqual(cheapest.this_survival, self.costs.optimum, places=9)

    def test_the_cheapest_team_now_is_the_planner_top_pick(self):
        top = {t.team for t in self.costs.cheapest_now(3)}
        self.assertIn(optimize(self.board).picks[0].team, top)


class TestWinTotals(unittest.TestCase):
    def setUp(self):
        self.board = load("data/survivor_2026.json")

    def test_solved_ratings_reproduce_the_posted_totals(self):
        totals = {"BAL": 11.5, "LAR": 11.5, "SEA": 10.5, "ARI": 4.5,
                  "MIA": 4.5, "LV": 5.5, "NYJ": 5.5}
        fit_ = solve_totals(self.board, totals)
        got = expected_wins(self.board, fit_.ratings)
        for team, target in totals.items():
            self.assertAlmostEqual(got[team], target, places=2)

    def test_expected_wins_sum_to_one_per_game(self):
        total = sum(expected_wins(self.board, {}).values())
        self.assertAlmostEqual(total, 272, places=6)

    def test_a_harder_schedule_earns_a_higher_rating_for_the_same_total(self):
        """The whole point of inverting totals against the real schedule."""
        fit_ = solve_totals(self.board, {"BAL": 11.5, "LAR": 11.5})
        self.assertNotAlmostEqual(fit_.ratings["BAL"], fit_.ratings["LAR"], places=2)

    def test_partial_totals_are_ignored_by_the_pipeline(self):
        board = load("data/survivor_2026.json")
        _r, notes = build_ratings(board, "data/prior_2026.json",
                                  "data/win_totals_2026.json")
        self.assertTrue(any("IGNORED" in n for n in notes))


class TestPrior(unittest.TestCase):
    # Hold out one week at a time and predict its posted lines.  A single week
    # is 16 games and noisy enough that its margin swings a lot as lines move,
    # so every assertion below averages the weeks rather than trusting one.
    HOLDOUTS = ((2, (1,)), (3, (1, 2)))

    def _holdout_mae(self, prior, hold, train):
        import copy as _copy
        from survivor.model import spread_from_prob
        board = load("data/survivor_2026.json")
        truth = [(g.home, g.away,
                  spread_from_prob(g.home_prob) if g.home_prob is not None else g.home_spread)
                 for w in board.weeks if w.number == hold for g in w.games
                 if g.home_prob is not None or g.home_spread is not None]
        train_board = _copy.deepcopy(board)
        for w in train_board.weeks:
            if w.number not in train:
                for g in w.games:
                    g.home_spread = g.home_prob = None
        r = fit(train_board, prior=prior)
        return sum(abs(r.spread(h, a) - s) for h, a, s in truth) / len(truth)

    def _mean_mae(self, prior):
        errs = [self._holdout_mae(prior, hold, train) for hold, train in self.HOLDOUTS]
        return sum(errs) / len(errs)

    def test_the_prior_beats_no_prior(self):
        from survivor.pipeline import load_prior
        with_prior = self._mean_mae(load_prior("data/prior_2026.json"))
        without = self._mean_mae(None)
        self.assertLess(with_prior, without * 0.8)

    def test_the_prior_beats_a_home_field_only_baseline(self):
        from survivor.model import HOME_FIELD, spread_from_prob
        from survivor.pipeline import load_prior
        board = load("data/survivor_2026.json")
        base = []
        for hold, _train in self.HOLDOUTS:
            truth = [spread_from_prob(g.home_prob) if g.home_prob is not None else g.home_spread
                     for w in board.weeks if w.number == hold for g in w.games
                     if g.home_prob is not None or g.home_spread is not None]
            base.append(sum(abs(HOME_FIELD - s) for s in truth) / len(truth))
        self.assertLess(self._mean_mae(load_prior("data/prior_2026.json")),
                        sum(base) / len(base) * 0.6)

    def test_the_prior_helps_on_every_holdout_not_just_on_average(self):
        from survivor.pipeline import load_prior
        prior = load_prior("data/prior_2026.json")
        for hold, train in self.HOLDOUTS:
            self.assertLess(self._holdout_mae(prior, hold, train),
                            self._holdout_mae(None, hold, train),
                            f"prior did not help on the week {hold} holdout")

    def test_prior_covers_all_32_teams(self):
        from survivor.pipeline import load_prior
        self.assertEqual(len(load_prior("data/prior_2026.json")), 32)


class TestTwoEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from survivor.multi import build_pair
        cls.board = load("data/survivor_2026.json")
        build_ratings(cls.board, "data/prior_2026.json", "data/win_totals_2026.json")
        cls.build_pair = staticmethod(build_pair)

    def test_diverging_at_week_two_shares_nothing(self):
        a, b = self.build_pair(self.board, 2)
        same = [x.week for x, y in zip(a.plan.picks, b.plan.picks) if x.team == y.team]
        self.assertEqual(same, [])

    def test_a_later_divergence_shares_the_prefix_exactly(self):
        a, b = self.build_pair(self.board, 6)
        for x, y in zip(a.plan.picks, b.plan.picks):
            if x.week < 6:
                self.assertEqual(x.team, y.team)

    def test_entries_never_make_the_same_pick_after_diverging(self):
        for d in (2, 5, 9):
            a, b = self.build_pair(self.board, d)
            bw = {p.week: p.team for p in b.plan.picks}
            for x in a.plan.picks:
                if x.week >= d and x.week in bw:
                    self.assertNotEqual(x.team, bw[x.week])

    def test_each_entry_still_uses_every_team_at_most_once(self):
        a, b = self.build_pair(self.board, 2)
        for entry in (a, b):
            teams = [p.team for p in entry.plan.picks]
            self.assertEqual(len(teams), len(set(teams)))

    def test_two_entries_beat_one(self):
        from survivor.multi import simulate_pair
        a, b = self.build_pair(self.board, 2)
        r = simulate_pair(self.board, a, b, sims=30000)
        self.assertGreater(r.p_at_least_one, r.p_a)
        self.assertGreater(r.p_at_least_one, r.p_b)

    def test_at_least_one_is_bounded_by_inclusion_exclusion(self):
        from survivor.multi import simulate_pair
        a, b = self.build_pair(self.board, 2)
        r = simulate_pair(self.board, a, b, sims=30000)
        self.assertAlmostEqual(r.p_at_least_one, r.p_a + r.p_b - r.p_both, places=9)

    def test_identical_entries_add_nothing(self):
        """Sharing every pick means one entry's outcome, twice."""
        from survivor.multi import Entry, simulate_pair
        plan = optimize(self.board)
        r = simulate_pair(self.board, Entry("A", plan), Entry("B", plan), sims=20000)
        self.assertAlmostEqual(r.p_at_least_one, r.p_a, places=9)
        self.assertAlmostEqual(r.p_both, r.p_a, places=9)

    def test_league_b_plans_from_its_own_history_once_recorded(self):
        from survivor.multi import build_pair
        board = load("data/survivor_2026.json")
        build_ratings(board, "data/prior_2026.json", "data/win_totals_2026.json")
        board.used = {1: ["PIT"], 2: ["SF"]}
        board.used_b = {2: ["TB"]}
        a, b = build_pair(board, 2)
        self.assertNotIn("SF", [p.team for p in a.plan.picks])   # A spent it
        self.assertNotIn("TB", [p.team for p in b.plan.picks])   # B spent it
        # Different weeks are different games, so B may still use SF later.
        self.assertEqual([p.week for p in b.plan.picks][0], 3)

    def test_recorded_entries_still_never_clash_in_a_week(self):
        from survivor.multi import build_pair
        board = load("data/survivor_2026.json")
        build_ratings(board, "data/prior_2026.json", "data/win_totals_2026.json")
        board.used, board.used_b = {1: ["PIT"], 2: ["SF"]}, {2: ["TB"]}
        a, b = build_pair(board, 2)
        bw = {p.week: p.team for p in b.plan.picks}
        for p in a.plan.picks:
            if p.week in bw:
                self.assertNotEqual(p.team, bw[p.week])

    def test_diverging_early_beats_diverging_late(self):
        """Compared on weeks survived, not on P(perfect season): with eight
        double weeks that probability is ~0.1%, where 40k sims is pure noise."""
        from survivor.multi import simulate_pair
        early = simulate_pair(self.board, *self.build_pair(self.board, 2),
                              sims=20000, seed=7)
        late = simulate_pair(self.board, *self.build_pair(self.board, 10),
                             sims=20000, seed=7)
        self.assertGreater(early.either_alive[5], late.either_alive[5])


class TestDoublePickWeeks(unittest.TestCase):
    """Weeks that demand two winners, both of which must come home."""

    @classmethod
    def setUpClass(cls):
        cls.board = load("data/survivor_2026.json")
        build_ratings(cls.board, "data/prior_2026.json", "data/win_totals_2026.json")
        cls.plan = optimize(cls.board)

    def test_the_pool_rule_is_loaded(self):
        doubles = {w.number for w in self.board.future_weeks() if w.picks_required == 2}
        self.assertEqual(doubles, {3, 6, 9, 12, 13, 14, 15, 16})

    def test_one_pick_per_required_slot(self):
        for wk_num, picks in self.plan.by_week().items():
            wk = next(w for w in self.board.weeks if w.number == wk_num)
            self.assertEqual(len(picks), wk.picks_required)

    def test_total_picks_match_what_the_season_demands(self):
        self.assertEqual(len(self.plan.picks), self.board.picks_needed())

    def test_no_team_is_used_twice_across_the_whole_plan(self):
        teams = [p.team for p in self.plan.picks]
        self.assertEqual(len(teams), len(set(teams)))

    def test_a_double_week_never_picks_the_same_team_twice(self):
        for picks in self.plan.by_week().values():
            self.assertEqual(len({p.team for p in picks}), len(picks))

    def test_survival_is_the_product_of_every_pick(self):
        prod = 1.0
        for p in self.plan.picks:
            prod *= p.prob
        self.assertAlmostEqual(self.plan.survival, prod, places=12)

    def test_survival_curve_has_one_point_per_week_not_per_pick(self):
        curve = self.plan.survival_curve()
        self.assertEqual(len(curve), len(self.plan.by_week()))
        self.assertEqual([w for w, _ in curve], sorted(self.plan.by_week()))

    def test_doubling_a_week_can_only_hurt(self):
        import copy as _copy
        relaxed = _copy.deepcopy(self.board)
        for w in relaxed.weeks:
            w.picks_required = 1
        self.assertGreater(optimize(relaxed).survival, self.plan.survival)

    def test_forcing_a_pair_is_respected(self):
        plan = optimize(self.board, force={3: ["KC", "NYG"]})
        self.assertEqual({p.team for p in plan.picks if p.week == 3}, {"KC", "NYG"})

    def test_forcing_one_team_leaves_the_other_slot_free(self):
        plan = optimize(self.board, force={3: "KC"})
        wk3 = [p.team for p in plan.picks if p.week == 3]
        self.assertIn("KC", wk3)
        self.assertEqual(len(wk3), 2)

    def test_forcing_too_many_teams_is_refused(self):
        with self.assertRaises(ValueError):
            optimize(self.board, force={4: ["KC", "NYG"]})   # week 4 takes one

    def test_no_forced_pair_beats_the_free_optimum(self):
        from survivor.plan import best_combinations
        for _combo, _wp, surv in best_combinations(self.board, top=6):
            self.assertLessEqual(surv, self.plan.survival + 1e-12)

    def test_the_best_combination_matches_the_plan(self):
        from survivor.plan import best_combinations
        best = best_combinations(self.board, top=1)[0][0]
        self.assertEqual(set(best), {p.team for p in self.plan.picks if p.week == 3})

    def test_simulation_still_tracks_the_analytic_value(self):
        from survivor.simulate import simulate_static
        r = simulate_static(self.board, self.plan, sims=60000,
                            model_error=False, seed=1)
        self.assertAlmostEqual(r.overall, self.plan.survival, delta=4 * r.se + 1e-5)

    def test_board_warns_that_slack_is_nearly_gone(self):
        self.assertTrue(any("spare" in w or "IMPOSSIBLE" in w
                            for w in self.board.warnings()))


class TestBoardRefreshKeepsConfig(unittest.TestCase):
    """A refresh once wiped the pool rule. It must not happen again."""

    def setUp(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import fetch_grid
        self.merge = fetch_grid.merge

    def test_double_weeks_survive_a_refresh(self):
        existing = {"season": 2026, "double_weeks": [3, 6], "used": {"1": ["PIT"]},
                    "weeks": {"1": {"games": []}}}
        out, kept = self.merge(existing, {"2": {"games": []}}, 2026)
        self.assertEqual(out["double_weeks"], [3, 6])
        self.assertIn("double_weeks", kept)

    def test_picks_and_adjustments_survive_a_refresh(self):
        existing = {"used": {"1": ["PIT"]}, "used_b": {"2": ["TB"]},
                    "adjustments": [{"week": 3, "team": "NYG", "win_prob": 0.5}],
                    "entries": 40}
        out, _kept = self.merge(existing, {"3": {"games": []}}, 2026)
        self.assertEqual(out["used"], {"1": ["PIT"]})
        self.assertEqual(out["used_b"], {"2": ["TB"]})
        self.assertEqual(out["adjustments"][0]["team"], "NYG")
        self.assertEqual(out["entries"], 40)

    def test_any_future_key_survives_a_refresh(self):
        out, kept = self.merge({"some_new_pool_rule": 123}, {"1": {"games": []}}, 2026)
        self.assertEqual(out["some_new_pool_rule"], 123)
        self.assertIn("some_new_pool_rule", kept)

    def test_the_fetch_still_replaces_the_schedule(self):
        out, _ = self.merge({"weeks": {"1": {"games": ["stale"]}}},
                            {"1": {"games": ["fresh"]}}, 2026)
        self.assertEqual(out["weeks"]["1"]["games"], ["fresh"])


class TestAdjustments(unittest.TestCase):
    """Hand-set prices for news the stored line may not carry yet."""

    def _board(self, adjustments):
        board = load("data/survivor_2026.json")
        board.adjustments = adjustments
        build_ratings(board, "data/prior_2026.json", "data/win_totals_2026.json")
        return board

    def test_an_override_changes_exactly_the_game_it_names(self):
        board = self._board([{"week": 3, "team": "NYG", "win_prob": 0.40,
                              "reason": "test"}])
        wk3 = next(w for w in board.weeks if w.number == 3)
        self.assertAlmostEqual(wk3.game_for("NYG").prob_for("NYG"), 0.40, places=6)
        self.assertAlmostEqual(wk3.game_for("TEN").prob_for("TEN"), 0.60, places=6)

    def test_an_override_does_not_leak_into_other_weeks(self):
        plain = self._board([])
        tweaked = self._board([{"week": 3, "team": "NYG", "win_prob": 0.40}])
        for wk in (15, 17):
            a = next(w for w in plain.weeks if w.number == wk).game_for("NYG")
            b = next(w for w in tweaked.weeks if w.number == wk).game_for("NYG")
            if a and b:
                self.assertAlmostEqual(a.prob_for("NYG"), b.prob_for("NYG"), places=9)

    def test_overrides_are_reported_not_silent(self):
        board = load("data/survivor_2026.json")
        board.adjustments = [{"week": 3, "team": "NYG", "win_prob": 0.4,
                              "reason": "QB out"}]
        _r, notes = build_ratings(board, "data/prior_2026.json",
                                  "data/win_totals_2026.json")
        self.assertTrue(any("OVERRIDE" in n and "QB out" in n for n in notes))

    def test_an_override_on_a_team_with_no_game_is_reported(self):
        board = load("data/survivor_2026.json")
        board.adjustments = [{"week": 3, "team": "ZZZ", "win_prob": 0.4}]
        _r, notes = build_ratings(board, "data/prior_2026.json",
                                  "data/win_totals_2026.json")
        self.assertTrue(any("IGNORED" in n for n in notes))

    def test_derating_a_team_never_helps_a_plan_that_uses_it(self):
        """An override moves BOTH sides of the game, so the overall optimum can
        rise -- derate the Giants far enough and Tennessee becomes pickable.
        The monotonic claim is about plans that actually use the derated team."""
        plain = optimize(self._board([]), force={3: "NYG"}).survival
        worse = optimize(self._board([{"week": 3, "team": "NYG", "win_prob": 0.40}]),
                         force={3: "NYG"}).survival
        self.assertLess(worse, plain)

    def test_an_override_lifts_the_opponent_by_the_same_amount(self):
        board = self._board([{"week": 3, "team": "NYG", "win_prob": 0.40}])
        wk3 = next(w for w in board.weeks if w.number == 3)
        self.assertAlmostEqual(wk3.game_for("NYG").prob_for("NYG")
                               + wk3.game_for("TEN").prob_for("TEN"), 1.0, places=9)


class TestDiscountObjective(unittest.TestCase):
    def setUp(self):
        self.board = load("data/survivor_2026.json")
        build_ratings(self.board, "data/prior_2026.json", "data/win_totals_2026.json")

    def test_combinations_respect_the_discount(self):
        """A discounted comparison must score discounted plans, or the cost
        column comes out negative against a differently-scored optimum."""
        from survivor.plan import best_combinations
        for disc in (1.0, 0.97):
            combos = best_combinations(self.board, top=5, discount=disc)
            best = combos[0][2]
            for _c, _wp, surv in combos:
                self.assertLessEqual(surv, best + 1e-12)

    def test_front_loading_prefers_a_safer_current_week(self):
        from survivor.plan import best_combinations
        season = best_combinations(self.board, top=1, discount=1.0)[0]
        front = best_combinations(self.board, top=1, discount=0.9)[0]
        self.assertGreaterEqual(front[1], season[1] - 1e-9)


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

    def test_week_one_pick_is_recorded_and_spent(self):
        self.assertEqual(self.board.used[1], ["PIT"])
        self.assertIn("PIT", self.board.used_teams)

    def test_used_weeks_are_contiguous_from_week_one(self):
        weeks = sorted(self.board.used)
        self.assertEqual(weeks, list(range(1, len(weeks) + 1)))

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
        """Week 2 has been played, so these games are only reachable with
        include_played -- the closing prices must survive the result landing."""
        wk2 = [w for w in self.board.weeks if w.number == 2][0]
        # Sourced from Week 2 writeups: SF ~85%, BAL ~74%.
        sf = wk2.game_for("SF", include_played=True)
        bal = wk2.game_for("BAL", include_played=True)
        self.assertAlmostEqual(sf.prob_for("SF"), 0.85, delta=0.03)
        self.assertAlmostEqual(bal.prob_for("BAL"), 0.74, delta=0.03)

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
