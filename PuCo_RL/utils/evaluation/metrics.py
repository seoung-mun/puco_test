import numpy as np
import trueskill
from collections import defaultdict

class TrueSkillTracker:
    def __init__(self, agent_names):
        # We start with default TrueSkill environment (mu=25.0, sigma=8.333)
        self.env = trueskill.TrueSkill(draw_probability=0.0)
        self.ratings = {name: self.env.create_rating() for name in agent_names}

    def update(self, ranks):
        """
        ranks is a dict: {agent_name: rank_integer}. 
        rank_integer is 1 for 1st place, 2 for 2nd, etc. Tie uses same rank.
        """
        names = list(ranks.keys())
        rating_groups = [[self.ratings[name]] for name in names]
        rank_list = [ranks[name] for name in names]
        
        # update TrueSkill returns list of lists corresponding to rating_groups
        new_rating_groups = self.env.rate(rating_groups, ranks=rank_list)
        
        for i, name in enumerate(names):
            self.ratings[name] = new_rating_groups[i][0]

    def get_ratings_dict(self):
        return {name: {"mu": r.mu, "sigma": r.sigma} for name, r in self.ratings.items()}


class VPMarginTracker:
    def __init__(self, agent_names):
        self.vp_margins = {name: [] for name in agent_names}

    def update(self, scores):
        """
        scores is a dict: {agent_name: vp_score_float}
        """
        total_vp = sum(scores.values())
        n = len(scores)
        
        for name, vp in scores.items():
            others_avg = (total_vp - vp) / (n - 1)
            margin = vp - others_avg
            self.vp_margins[name].append(margin)

    def get_average_margins(self):
        return {name: np.mean(margins) if margins else 0.0 for name, margins in self.vp_margins.items()}


class RoleEntropyTracker:
    def __init__(self, agent_names):
        self.role_counts = {name: defaultdict(int) for name in agent_names}

    def update(self, agent_name, role_idx):
        self.role_counts[agent_name][role_idx] += 1

    def get_entropies(self):
        entropies = {}
        for name, counts in self.role_counts.items():
            total = sum(counts.values())
            if total == 0:
                entropies[name] = 0.0
                continue
            
            p = np.array(list(counts.values())) / total
            entropy = -np.sum(p * np.log(p + 1e-9))
            entropies[name] = float(entropy)
        return entropies
