import numpy as np
import trueskill
from collections import defaultdict


class TrueSkillTracker:
    def __init__(self, agent_names: list[str]):
        self.env = trueskill.TrueSkill(draw_probability=0.0)
        self.ratings = {name: self.env.create_rating() for name in agent_names}

    def update(self, ranks: dict[str, int]):
        """ranks: {agent_name: rank_int}  (1 = first place)"""
        names = list(ranks.keys())
        rating_groups = [[self.ratings[name]] for name in names]
        rank_list = [ranks[name] for name in names]
        new_groups = self.env.rate(rating_groups, ranks=rank_list)
        for i, name in enumerate(names):
            self.ratings[name] = new_groups[i][0]

    def get_ratings_dict(self) -> dict:
        return {name: {"mu": r.mu, "sigma": r.sigma} for name, r in self.ratings.items()}


class VPMarginTracker:
    def __init__(self, agent_names: list[str]):
        self.vp_margins: dict[str, list[float]] = {name: [] for name in agent_names}

    def update(self, scores: dict[str, float]):
        """scores: {agent_name: total_vp}"""
        total = sum(scores.values())
        n = len(scores)
        for name, vp in scores.items():
            others_avg = (total - vp) / max(1, n - 1)
            self.vp_margins[name].append(vp - others_avg)

    def get_average_margins(self) -> dict[str, float]:
        return {
            name: float(np.mean(margins)) if margins else 0.0
            for name, margins in self.vp_margins.items()
        }


class VPDecompositionTracker:
    """Tracks shipping VP (vp_chips) vs building VP per agent."""

    def __init__(self, agent_names: list[str]):
        self.shipping_vp: dict[str, list[float]] = {name: [] for name in agent_names}
        self.building_vp: dict[str, list[float]] = {name: [] for name in agent_names}

    def update(self, vp_decomp: dict[str, dict]):
        """vp_decomp: {agent_name: {"shipping": int, "building": int}}"""
        for name, vals in vp_decomp.items():
            if name in self.shipping_vp:
                self.shipping_vp[name].append(vals["shipping"])
                self.building_vp[name].append(vals["building"])

    def get_averages(self) -> dict[str, dict]:
        return {
            name: {
                "shipping": float(np.mean(self.shipping_vp[name])) if self.shipping_vp[name] else 0.0,
                "building": float(np.mean(self.building_vp[name])) if self.building_vp[name] else 0.0,
            }
            for name in self.shipping_vp
        }


class RoleEntropyTracker:
    """Computes Shannon entropy of each agent's role selection distribution."""

    def __init__(self, agent_names: list[str]):
        # role index 0-7 matches Role enum
        self.role_counts: dict[str, np.ndarray] = {
            name: np.zeros(8, dtype=np.int64) for name in agent_names
        }

    def update(self, role_counts_per_game: dict[str, list]):
        """role_counts_per_game: {agent_name: [count_role0, ..., count_role7]}"""
        for name, counts in role_counts_per_game.items():
            if name in self.role_counts:
                self.role_counts[name] += np.array(counts, dtype=np.int64)

    def get_entropies(self) -> dict[str, float]:
        entropies = {}
        for name, counts in self.role_counts.items():
            total = counts.sum()
            if total == 0:
                entropies[name] = 0.0
                continue
            p = counts / total
            entropies[name] = float(-np.sum(p * np.log(p + 1e-12)))
        return entropies

    def get_distributions(self) -> dict[str, np.ndarray]:
        """Normalised role selection frequencies (0-7)."""
        result = {}
        for name, counts in self.role_counts.items():
            total = counts.sum()
            result[name] = counts / max(1, total)
        return result
