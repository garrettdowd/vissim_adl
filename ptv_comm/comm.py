from collections import namedtuple
import random
import pandas as pd

""" Intended Use Documentation Here

    message delays can be used, but anything shorter than the sim time step
        is trivial and can be ignored. This should be the case given a normal simulation time step
        and a max communication distance of 1-2km
    Agents must have a receiveMsg(msg_type, payload) function
    Agents must have a unique "id" property - agent.id
"""

def setup(_Vissim, _msg_types=-1):
    global Vissim
    global msg_types
    global SIM_RES
    global all_comms

    Vissim = _Vissim
    all_comms = []
    if _msg_types == -1:
        # try to conform with SAE J2735 and other applicable standards
        msg_types = {
            'location': 0,  # [x,y,z] coordinates
            'BSM':      1,  # [time, message #, location, speed, heading, acceleration]
            'SPAT':     2,
            'TIM':      3,  # can be used for a lot of stuff, use ITIS phrases
            'EVA':      4,  # emergency vehicle alert
            'ICA':      5,  # intersection collision avoidance
            'PSM':      6,  # personal safety message, for vulnerable road users
            'PVD':      10, # probe vehicle data, send data to RSU
            'RSA':      20, # road side alert
        }
    else:
        msg_types = _msg_types

    #################################################################################
    #################################################################################
    SIM_RES = Vissim.Simulation.AttValue('SimRes')

def update():
    for comm in all_comms:
        comm.update()


def saveResults(filepath):
    column_comms = ['timestamp', 'sender_id', 'recipient_id', 'msg_type', 'payload', 'delay', 'dropped']
    df = []
    for comm in all_comms:
        for msg in comm.all_messages:
            df_d = {
                'timestamp': msg.timestamp,
                'sender_id': msg.sender_id,
                'recipient_id': msg.recipient_id,
                'msg_type': msg.msg_type,
                'payload': msg.payload,
                'delay': msg.delay,
                'dropped': msg.dropped
            }
            df.append(df_d)

    df = pd.DataFrame(df)
    df = df.reindex(columns=column_comms)  # ensure columns are in correct order
    # df = df.iloc[::-1] # reverse order of rows
    df.to_csv(filepath, encoding='utf-8', index=False)



Message = namedtuple('Message', 'timestamp, sender_id, recipient_id, msg_type, payload, delay, dropped')
class newComm:
    def __init__(self, list_of_lists_of_agents, reliability_pct = 1 , delay_gauss_mean = 0, delay_guass_stddev = 0):
        # define a unique id
        if not all_comms:
            self.id = 0
        else:
            max_id = max([comm.id for comm in all_comms])
            self.id = max_id + 1
        self.agents = list_of_lists_of_agents
        self.reliability_pct = reliability_pct
        self.delay_gauss_mean = delay_gauss_mean
        self.delay_guass_stddev = delay_guass_stddev
        self.s = Sched(self._timefunc)
        self.all_messages = []
        all_comms.append(self)

    """ Intended Use Documentation Here
    broadcast_location = [X,Y] or [X,Y,Z] - must be given as it determines which agents will be in range to receive the message
    msg_type = integer - message types defined when instantiating the class
    payload = string - parsing of payload is left to receiving agents
    recipient_id = -1 will broadcast the message to all agents within range
    sender_id = -1 means that the message is being sent anonymously

    """
    # update should be called every loop. This allows delayed messages to be sent out
    def update(self):
        self.s.update()

    def broadcast(self, broadcast_location, comm_range, msg_type, payload, recipient_id = -1, sender_id = -1):
        # recipient_id must be unique among all agents
        if recipient_id == -1: # broadcast to all agents including self
            for agent_list in self.agents:
                for agent in agent_list:
                    msg = self._createMsg(sender_id, agent.id, msg_type, payload, broadcast_location, agent.position(), comm_range)
                    self._scheduleMsg(msg)
        else: # broadcast only to desired recipient_id
            for agent_list in self.agents:
                agent = next((agent for agent in agent_list if agent.id==recipient_id), None)
                if agent != None:
                    msg = self._createMsg(sender_id, agent.id, msg_type, payload, broadcast_location, agent.position(), comm_range)
                    self._scheduleMsg(msg)
                else:
                    print("When broadcasting a message, given recipient_id #"+str(recipient_id)+" does not exist")
                    # Vissim.Simulation.Stop()

    def _createMsg(self, sender_id, recipient_id, msg_type, payload, loc1, loc2, comm_range):
        time = Vissim.Simulation.AttValue('SimSec')
        delay = self._delay()
        dist = self._dist(loc1,loc2)
        dropped = self._drop(dist, comm_range)
        msg =  Message(time, sender_id, recipient_id, msg_type, payload, delay, dropped)
        self.all_messages.append(msg)
        return msg

    def _scheduleMsg(self, message):
        if message.dropped == 0:
            if message.delay < SIM_RES:
                self._sendMsg(message)
            else:
                self.s.enter(message.delay,1,self._sendMsg,(message))

    def _sendMsg(self, message):
        for agent_list in self.agents:
            agent = next((agent for agent in agent_list if agent.id==message.recipient_id), None)
            if agent != None:
                agent.receiveMsg(message.sender_id, message.msg_type, message.payload)

    # maybe should be based on congestion?
    def _delay(self):
        return random.gauss(self.delay_gauss_mean, self.delay_guass_stddev)

    def _dist(self, loc1, loc2):
        if len(loc1) < 2 | len(loc1) > 3:
            print("Invalid location 1 for class Comm method _dist()")
            Vissim.Simulation.Stop()
        elif len(loc1) == 2:
            loc1.append(0)

        if len(loc2) < 2 | len(loc2) > 3:
            print("Invalid location 2 for class Comm method _dist()")
            Vissim.Simulation.Stop()
        if len(loc2) == 2:
            loc2.append(0)

        return (loc1[0] - loc2[0])**2 + (loc1[1] - loc2[1])**2 + (loc1[2] - loc2[2])**2 

    # this needs to be updated with an equation that can better model the chance of dropping messages based on distance
    def _drop(self, dist, comm_range):
        normalized_diff = (dist - comm_range)/comm_range
        # This is the function that calculates dropped message probability
        # Does not current function (zero cannot be raised to a negative power)
        # drop_chance = (1-self.reliability_pct)**(normalized_diff)-(1-self.reliability_pct) # https://www.desmos.com/calculator/w1g0o7umlq
        # if drop_chance > 1:
        #     return 0
        # elif drop_chance < 0:
        #     return 1
        # else:
        #     return random.randint(0,1)
        if normalized_diff > 0:
            return 0
        elif normalized_diff < 0:
            return 1

    def _timefunc(self):
        return float(Vissim.Simulation.AttValue('SimSec'))




""" Generic python module "Sched" will not work in this context
    Modify library slightly to work in this context
    Main diferences
        no delayfunc needed
        no run() method. Replaced with update() method that is called every loop
        "priority" not used because there is no real time context where events can be delayed past the intended delay time
        heapq not used. regular sorted list used instead
"""
Event = namedtuple('Event', 'time, priority, action, argument')
class Sched:
    def __init__(self,timefunc):
        self.time = timefunc
        self._queue = [] # sorted from next to last

    def enterabs(self, time, priority, action, argument):
        """Enter a new event in the queue at an absolute time.
        Returns an ID for the event which can be used to remove it,
        if necessary.
        """
        event = Event(time, priority, action, argument)
        self._queue.append(event)
        self._queue.sort(key=lambda x: x[1][0]) # sort by time
        return event # The ID

    def enter(self, delay, priority, action, argument):
        """A variant that specifies the time as a relative time.
        This is actually the more commonly used interface.
        """
        time = self.time() + delay
        return self.enterabs(time, priority, action, argument)

    def cancel(self, event):
        """Remove an event from the queue.
        This must be presented the ID as returned by enter().
        If the event is not in the queue, this raises ValueError.
        """
        self._queue.remove(event)

    def empty(self):
        """Check whether the queue is empty."""
        return not self._queue

    def update(self):
        now = self.time()
        while self._queue:
            time, priority, action, argument = self._queue[0]
            if now <= time:
                return
            else:
                self._queue.pop(0)
                action(*argument)
