import sys, os, time
DIR_LOC = os.path.dirname(os.path.abspath(__file__))
sys.path.append(DIR_LOC+"/..")
from blackscholes.dgm.DGMNet import DGMNet
from utils.Domain import Sampler1d
import tensorflow as tf
import numpy as np

class Euro1d:

    def __init__(self, domain, vol, ir, dividend, strike, cp_type):
        """
        cp_type (call/put type): 1 if call, -1 if put
        """
        self.p = lambda S, t: vol**2*S**2/2
        self.q = lambda S, t: (ir-dividend)*S
        self.ir = ir
        self.strike = strike
        self.cp_type = cp_type
        self.domain = domain
        self.sampler = Sampler1d(domain)

    def run(self, n_samples, steps_per_sample, n_layers=3, layer_width=50, n_interior=1000, n_boundary=100, n_terminal=100, saved_name=None):
        if not saved_name:
            saved_name = "Euro1d_{}.ckpt".format(time.strftime("%Y%m%d"))
        else:
            saved_name += ".ckpt"

        model = DGMNet(n_layers, layer_width, input_dim=1)
        self.model = model
        S_interior_tnsr = tf.placeholder(tf.float32, [None,1])
        t_interior_tnsr = tf.placeholder(tf.float32, [None,1])
        S_boundary_tnsr = tf.placeholder(tf.float32, [None,1])
        t_boundary_tnsr = tf.placeholder(tf.float32, [None,1])
        S_terminal_tnsr = tf.placeholder(tf.float32, [None,1])
        t_terminal_tnsr = tf.placeholder(tf.float32, [None,1])
        L1_tnsr, L2_tnsr, L3_tnsr = self.loss_func(model, S_interior_tnsr, t_interior_tnsr,\
            S_boundary_tnsr, t_boundary_tnsr, S_terminal_tnsr, t_terminal_tnsr)
        loss_tnsr = L1_tnsr + L2_tnsr + L3_tnsr

        V = self.model(S_interior_tnsr, t_interior_tnsr)

        global_step = tf.Variable(0, trainable=False)
        boundaries = [5000, 10000, 20000, 30000, 40000, 45000]
        values = [1e-4, 5e-5, 1e-5, 5e-6, 1e-6, 5e-7, 1e-7]
        learning_rate = tf.train.piecewise_constant(global_step, boundaries, values)
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(loss_tnsr)

        model_saver = tf.train.Saver()
        self.loss_vec, self.L1_vec, self.L2_vec, self.L3_vec = [], [], [], []
        with tf.Session() as sess:
            sess.run(tf.global_variables_initializer())
            for i in range(n_samples):
                S_interior, t_interior, S_boundary, t_boundary, S_terminal, t_terminal = \
                    self.sampler.run(n_interior, n_boundary, n_terminal)
                for _ in range(steps_per_sample):
                    loss, L1, L2, L3, _ = sess.run([loss_tnsr, L1_tnsr, L2_tnsr, L3_tnsr, optimizer],\
                        feed_dict={S_interior_tnsr: S_interior, t_interior_tnsr: t_interior,\
                                   S_boundary_tnsr: S_boundary, t_boundary_tnsr: t_boundary,\
                                   S_terminal_tnsr: S_terminal, t_terminal_tnsr: t_terminal})
                self.loss_vec.append(loss); self.L1_vec.append(L1); self.L2_vec.append(L2); self.L3_vec.append(L3)
                print("Iteration {}: Loss: {}; L1: {}; L2: {}; L3: {}".format(i, loss, L1, L2, L3))
            model_saver.save(sess, DIR_LOC+"/saved_models/"+saved_name)
            # S_plot = np.linspace(self.domain.a, self.domain.b, 20).reshape(-1, 1)
            # t_plot = 0*np.ones_like(S_plot)
            # fitted_optionValue = sess.run([V], feed_dict= {S_interior_tnsr: S_plot, t_interior_tnsr: t_plot})
            # print(fitted_optionValue)

    def restore(self, S, t, saved_name, n_layers=3, layer_width=50):
        self.model = DGMNet(n_layers, layer_width, input_dim=1)
        S_interior_tnsr = tf.placeholder(tf.float32, [None,1])
        t_interior_tnsr = tf.placeholder(tf.float32, [None,1])
        V = self.model(S_interior_tnsr, t_interior_tnsr)
        model_saver = tf.train.Saver()
        with tf.Session() as sess:
            model_saver.restore(sess, DIR_LOC+'/saved_models/{}.ckpt'.format(saved_name))
            fitted_optionValue = sess.run(V, feed_dict= {S_interior_tnsr: S, t_interior_tnsr: t})
            print("Model {}: {}".format(saved_name, fitted_optionValue.T))
            return fitted_optionValue.T
            
    def loss_func(self, model, S_interior, t_interior, S_boundary, t_boundary, S_terminal, t_terminal):
        ''' Compute total loss for training.
        
        Args:
            model:      DGMNet model object
            t_interior: sampled time points in the interior of the function's domain
            S_interior: sampled space points in the interior of the function's domain
            t_terminal: sampled time points at terminal point (vector of terminal times)
            S_terminal: sampled space points at terminal time
        ''' 
        # Loss term #1: PDE
        # compute function value and derivatives at current sampled points
        V = model(S_interior, t_interior)
        V_t = tf.gradients(V, t_interior)[0]
        V_s = tf.gradients(V, S_interior)[0]
        V_ss = tf.gradients(V_s, S_interior)[0]
        diff_V = V_t + self.p(S_interior, t_interior)*V_ss + self.q(S_interior, t_interior)*V_s - self.ir*V

        # compute average L2-norm of differential operator
        L1 = tf.reduce_mean(tf.square(diff_V)) 
        
        # Loss term #2: boundary condition
        fitted_bc_val = model(S_boundary, t_boundary)
        if self.cp_type == 1:
            target_bc_val = tf.where(S_boundary >= self.domain.b,\
                                      tf.math.multiply(S_boundary, tf.math.exp(-self.ir*t_boundary)),\
                                      tf.zeros_like(fitted_bc_val))
        else:
            target_bc_val = tf.where(S_boundary <= self.domain.a,\
                                      tf.math.multiply(self.strike, tf.math.exp(-self.ir*t_boundary)),\
                                      tf.zeros_like(fitted_bc_val))
        # target_bc_val = tf.zeros_like(fitted_bc_val)
        # print(fitted_bc_val); print(S_boundary); print(valuable_index); print(target_bc_val[valuable_index[0]]); print(S_boundary[valuable_index[0]])
        #target_bc_val[valuable_index] = 
        L2 = tf.reduce_mean(tf.square(fitted_bc_val - target_bc_val))
        
        # Loss term #3: initial/terminal condition
        target_payoff = tf.nn.relu(self.cp_type*(S_terminal - self.strike))
        fitted_payoff = model(S_terminal, t_terminal)
        
        L3 = tf.reduce_mean(tf.square(fitted_payoff - target_payoff))

        return L1, L2, L3