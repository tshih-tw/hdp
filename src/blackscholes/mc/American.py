import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../..")
from blackscholes.utils.Regression import Regression
import numpy as np

class American:
    """
    Multi-Dimensional American Option
    """
    def __init__(self, payoff_func, random_walk):
        """
        payoff: A function that takes ${asset_num} variables as input, returns the a scalar payoff
        random_walk: A random walk generator, e.g. GBM (geometric brownian motion)
        """
        self.payoff_func = payoff_func
        self.random_walk = random_walk
    
    def price(self, path_num=1000):
        self.simulation_result = self.random_walk.simulate(path_num)

        cashflow_matrix = np.zeros([path_num, self.random_walk.N+1])
        cur_price = list(map(lambda x: x[:, -1], self.simulation_result))
        cur_payoff = list(map(self.payoff_func, cur_price))
        cashflow_matrix[:, self.random_walk.N] = cur_payoff

        for t in range(self.random_walk.N-1, -1, -1):
            discounted_cashflow = self._get_discounted_cash_flow(t, cashflow_matrix, path_num)
            # Compute the discounted payoff
            r = Regression(self.simulation_result[:, :, t], discounted_cashflow, payoff_func=self.payoff_func)
            cur_price = list(map(lambda x: x[:, t], self.simulation_result))
            cur_payoff = list(map(self.payoff_func, cur_price))

    def _get_discounted_cash_flow(self, t, cashflow_matrix, path_num):
        discounted_cashflow = np.zeros(path_num)
        for j in range(self.random_walk.N, t, -1):
            for i in range(len(cashflow_matrix[:, j])):
                if discounted_cashflow[i] != 0: continue
                cashflow = cashflow_matrix[:, j][i]
                if cashflow != 0:
                    discounted_cashflow[i] = cashflow * np.exp((t-j)*self.random_walk.dt*self.random_walk.ir)
        return discounted_cashflow
