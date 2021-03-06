import tensorflow as tf 
from tensorflow.contrib.layers.python.layers import batch_norm as batch_norm
import numpy as np
import math
from detector import Detector
from program import Program
from message_passing import Message_passing

# Hyper Parameters
LAYER1_SIZE = 400
LAYER2_SIZE = 300
LEARNING_RATE = 1e-4
TAU = 0.001
BATCH_SIZE = 64

class ActorNetwork:
    """docstring for ActorNetwork"""
    def __init__(self,sess,state_dim,action_dim):

        self.sess = sess
        self.state_dim = state_dim
        self.action_dim = action_dim
        # create actor network
        self.state_input,self.action_output,self.net,self.is_training = self.create_network(state_dim,action_dim)

        # create target actor network
        self.target_state_input,self.target_action_output,self.target_update,self.target_is_training = self.create_target_network(state_dim,action_dim,self.net)

        # define training rules
        self.create_training_method()

        self.sess.run(tf.global_variables_initializer())

        self.update_target()
        #self.load_network()

    def create_training_method(self):
        self.q_gradient_input = tf.placeholder("float",[None,self.action_dim])
        self.parameters_gradients = tf.gradients(self.action_output,self.net,-self.q_gradient_input)
        self.optimizer = tf.train.AdamOptimizer(LEARNING_RATE).apply_gradients(zip(self.parameters_gradients,self.net))

    def create_network(self,state_dim,action_dim):
        layer1_size = LAYER1_SIZE
        layer2_size = LAYER2_SIZE

        state_input = tf.placeholder("float",[None,state_dim])
        program_order = tf.placeholder("float",[None,4]);
        self.program_order = program_order;
        #detector
        self.detector=Detector(self.sess,state_dim,5,15,state_input,"_action");
        Theta=self.detector.Theta;
        detector_params=self.detector.net;
        #program
        self.program=Program(self.sess,state_dim,5,15,Theta,program_order,"_action");
        p=self.program.p;
        #message_passing
        self.message_passing=Message_passing(self.sess,state_dim,5,15,p,state_input,150,64,64,"_action");
        state_input2 = self.message_passing.state_output;
        message_passing_params = self.message_passing.net;
        #get h
        state_input2 = tf.reshape(state_input2,[-1,5,150]);
        state_input2 = tf.unstack(state_input2,5,1);
        p=tf.unstack(p,5,1);
        h=0;
        for i in range(5):
          h+=tf.stack([p[i]]*150,1)*state_input2[i];

        #action net
        W1 = self.variable([150,action_dim],150)
        b1 = self.variable([action_dim],150)
        action_output=tf.tanh(tf.matmul(tf.tanh(h),W1)+b1);
        params = detector_params+message_passing_params+[W1,b1];

        return state_input,action_output,params,is_training

    def create_target_network(self,state_dim,action_dim,net):
        state_input = tf.placeholder("float",[None,state_dim])
        program_order = tf.placeholder("float",[None,4]);
        self.target_program_order = program_order;
        is_training = tf.placeholder(tf.bool)
        ema = tf.train.ExponentialMovingAverage(decay=1-TAU)
        target_update = ema.apply(net)
        target_net = [ema.average(x) for x in net]

        # params for each net
        d_net=target_net[:self.detector.params_num];
        m_net=target_net[self.detector.params_num:(self.detector.params_num+self.message_passing.params_num)];
        a_net=target_net[(self.detector.params_num+self.message_passing.params_num):];
        # run detector
        Theta=self.detector.run_target_nets(state_input,d_net);
        # run program
        p=self.program.run_target_nets(Theta,program_order);
        # run message_passing
        state_input2=self.message_passing.run_target_nets(state_input,p,m_net);
        #get h
        state_input2 = tf.reshape(state_input2,[-1,5,150]);
        state_input2 = tf.unstack(state_input2,5,1);
        p=tf.unstack(p,5,1);
        h=0;
        for i in range(5):
          h+=tf.stack([p[i]]*150,1)*state_input2[i];
       
        action_output=tf.tanh(tf.matmul(tf.tanh(h),a_net[0])+a_net[1]);

        return state_input,action_output,target_update,is_training

    def update_target(self):
        self.sess.run(self.target_update)

    def train(self,q_gradient_batch,state_batch,program_order_batch):
        self.sess.run(self.optimizer,feed_dict={
            self.q_gradient_input:q_gradient_batch,
            self.state_input:state_batch,
            self.program_order:program_order_batch,
            })

    def actions(self,state_batch,program_order_batch):
        return self.sess.run(self.action_output,feed_dict={
            self.state_input:state_batch,
            self.program_order:program_order_batch,
            })

    def action(self,state,program_order):
        return self.sess.run(self.action_output,feed_dict={
            self.state_input:[state],
            self.program_order:[program_order],
            })[0]


    def target_actions(self,state_batch,program_order_batch):
        return self.sess.run(self.target_action_output,feed_dict={
            self.target_state_input: state_batch,
            self.target_program_order:program_order_batch,
            })

    # f fan-in size
    def variable(self,shape,f):
        return tf.Variable(tf.random_uniform(shape,-1/math.sqrt(f),1/math.sqrt(f)))


    def batch_norm_layer(self,x,training_phase,scope_bn,activation=None):
        return tf.cond(training_phase, 
        lambda: tf.contrib.layers.batch_norm(x, activation_fn=activation, center=True, scale=True,
        updates_collections=None,is_training=True, reuse=None,scope=scope_bn,decay=0.9, epsilon=1e-5),
        lambda: tf.contrib.layers.batch_norm(x, activation_fn =activation, center=True, scale=True,
        updates_collections=None,is_training=False, reuse=True,scope=scope_bn,decay=0.9, epsilon=1e-5))
'''
    def load_network(self):
        self.saver = tf.train.Saver()
        checkpoint = tf.train.get_checkpoint_state("saved_actor_networks")
        if checkpoint and checkpoint.model_checkpoint_path:
            self.saver.restore(self.sess, checkpoint.model_checkpoint_path)
            print "Successfully loaded:", checkpoint.model_checkpoint_path
        else:
            print "Could not find old network weights"
    def save_network(self,time_step):
        print 'save actor-network...',time_step
        self.saver.save(self.sess, 'saved_actor_networks/' + 'actor-network', global_step = time_step)

'''

        
