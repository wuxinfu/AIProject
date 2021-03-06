from __future__ import print_function


from builtins import range
import MalmoPython
import json
import logging
import math
import os
import random
import sys
import time
import malmoutils
import expectimax
import minimax
import reflex
import hiddenMarkov
#algorithms = {"reflex": reflex.reflex, "hiddenMarkov": hiddenMarkov.hiddenMarkov, "minimax":minimax.minimax, "expectimax": expectimax.expectimax}
algorithms = {"reflex": reflex.reflex}
assert len(sys.argv) == 4, "Wrong number of arguments, the form is: mapSize, agent algorithm, enemy alogrithm" 




malmoutils.fix_print()

# -- set up two agent hosts --
agent_host1 = MalmoPython.AgentHost()
agent_host2 = MalmoPython.AgentHost()
map_size = str(sys.argv[1])

agentAlgo =  algorithms[sys.argv[2]]
enemyAlgo = algorithms[sys.argv[3]]

# Use agent_host1 for parsing the command-line options.
# (This is why agent_host1 is passed in to all the subsequent malmoutils calls, even for
# agent 2's setup.)
malmoutils.parse_command_line(agent_host1)


missionXML='''<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
            <Mission xmlns="http://ProjectMalmo.microsoft.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            
              <About>
                <Summary>Hello world!</Summary>
              </About>
              
              <ServerSection>
                <ServerInitialConditions>
                  <Time>
                    <StartTime>12000</StartTime>
                    <AllowPassageOfTime>false</AllowPassageOfTime>
                  </Time>
                </ServerInitialConditions>
                <ServerHandlers>
                  <FlatWorldGenerator generatorString="3;7,220*1,5*3,2;3;,biome_1"/>
                  <DrawingDecorator>
                    <!-- coordinates for cuboid are inclusive -->
                    <DrawCuboid x1="1" y1="45" z1="1" x2=''' + '"' + map_size + '"' + ''' y2="300" z2=''' + '"'+ map_size + '"'+  ''' type="air" />            <!-- limits of our arena -->
                    <DrawCuboid x1="1" y1="40" z1="1" x2='''+ '"'+ map_size + '"'+ ''' y2="44" z2='''+ '"'+ map_size+ '"' +''' type="lava" />           <!-- lava floor -->
                    <DrawCuboid x1="1"  y1="46" z1="1"  x2='''+ '"'+ map_size+ '"'+ ''' y2="46" z2='''+ '"'+ map_size+ '"' +''' type="snow" />
                  </DrawingDecorator>
                  <ServerQuitFromTimeUp timeLimitMs="300000"/>
                  
                </ServerHandlers>
              </ServerSection>
              
              <AgentSection mode="Survival">
                <Name>Agent</Name>
                <AgentStart>
                    <Inventory>
                        <InventoryItem slot="0" type="diamond_shovel"/>
                    </Inventory>
                    <Placement x="1.5" y="47.0" z="1.5" pitch="50" yaw="0"/>
                </AgentStart>
                <AgentHandlers>
                  <ObservationFromFullStats/>
                  <DiscreteMovementCommands/>
                </AgentHandlers>
              </AgentSection>
              
              <AgentSection mode="Survival">
                <Name>Enemy</Name>
                <AgentStart>
                    <Inventory>
                        <InventoryItem slot="0" type="diamond_shovel"/>
                    </Inventory>
                    <Placement x='''+ '"'+ str(float(map_size) + 0.5) + '"'+ ''' y="47.0" z='''+ '"'+ str(float(map_size) + 0.5)+ '"'+ ''' pitch="50" yaw="180"/>
                </AgentStart>
                
                <AgentHandlers>
                  <ObservationFromFullStats/>
                  <DiscreteMovementCommands/>
                  <RewardForTouchingBlockType>
                    <Block reward="-100.0" type="lava" behaviour="onceOnly"/>
                  </RewardForTouchingBlockType>
                  <AgentQuitFromTouchingBlockType>
                    <Block type="lava" />
                  </AgentQuitFromTouchingBlockType>
                </AgentHandlers>
              </AgentSection>
            </Mission>'''

# Create default Malmo objects:
my_mission = MalmoPython.MissionSpec(missionXML, True)

client_pool = MalmoPython.ClientPool()
client_pool.add( MalmoPython.ClientInfo('127.0.0.1',10000) )
client_pool.add( MalmoPython.ClientInfo('127.0.0.1',10001) )

MalmoPython.setLogging("", MalmoPython.LoggingSeverityLevel.LOG_OFF)
my_mission_record = MalmoPython.MissionRecordSpec()

def safeStartMission(agent_host, mission, client_pool, recording, role, experimentId):
    used_attempts = 0
    max_attempts = 5
    print("Calling startMission for role", role)
    while True:
        try:
            agent_host.startMission(mission, client_pool, recording, role, experimentId)
            break
        except MalmoPython.MissionException as e:
            errorCode = e.details.errorCode
            if errorCode == MalmoPython.MissionErrorCode.MISSION_SERVER_WARMING_UP:
                print("Server not quite ready yet - waiting...")
                time.sleep(2)
            elif errorCode == MalmoPython.MissionErrorCode.MISSION_INSUFFICIENT_CLIENTS_AVAILABLE:
                print("Not enough available Minecraft instances running.")
                used_attempts += 1
                if used_attempts < max_attempts:
                    print("Will wait in case they are starting up.", max_attempts - used_attempts, "attempts left.")
                    time.sleep(2)
            elif errorCode == MalmoPython.MissionErrorCode.MISSION_SERVER_NOT_FOUND:
                print("Server not found - has the mission with role 0 been started yet?")
                used_attempts += 1
                if used_attempts < max_attempts:
                    print("Will wait and retry.", max_attempts - used_attempts, "attempts left.")
                    time.sleep(2)
            else:
                print("Other error:", e.message)
                print("Waiting will not help here - bailing immediately.")
                exit(1)
        if used_attempts == max_attempts:
            print("All chances used up - bailing now.")
            exit(1)
    print("startMission called okay.")

def safeWaitForStart(agent_hosts):
    print("Waiting for the mission to start", end=' ')
    start_flags = [False for a in agent_hosts]
    start_time = time.time()
    time_out = 120  # Allow two minutes for mission to start.
    while not all(start_flags) and time.time() - start_time < time_out:
        states = [a.peekWorldState() for a in agent_hosts]
        start_flags = [w.has_mission_begun for w in states]
        errors = [e for w in states for e in w.errors]
        if len(errors) > 0:
            print("Errors waiting for mission start:")
            for e in errors:
                print(e.text)
            print("Bailing now.")
            exit(1)
        time.sleep(0.1)
        print(".", end=' ')
    print()
    if time.time() - start_time >= time_out:
        print("Timed out waiting for mission to begin. Bailing.")
        exit(1)
    print("Mission has started.")

safeStartMission(agent_host1, my_mission, client_pool, my_mission_record, 0, '' )
safeStartMission(agent_host2, my_mission, client_pool, my_mission_record, 1, '' )
safeWaitForStart([agent_host1, agent_host2])

def movement(ah, direction):
    if direction == "north":
        ah.sendCommand("movenorth 1")
    if direction == "south":
        ah.sendCommand("movesouth 1")
    if direction == "west":
        ah.sendCommand("movewest 1")
    if direction == "east":
        ah.sendCommand("moveeast 1")
    time.sleep(0.1)
def attack(ah, index, enemy=False):
    #We are going to make it so the agent can only break the blocks immediately around them. 
    #So a location will be one of the 8 locations around it  
    #Enemy starts facing north (1), Agent starts facing south (3)
    # 0 1 0
    # 4 X 2
    # 0 3 0
    #print("Called with index {}".format(index))
    if enemy:
        if index ==1:
            print("Index 1")
            # time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
        if index ==2:
            print("Index 2")
            # time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
        if index == 4:
            print("Index 4")
            # time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
        if index == 3:
            print("Index 3")
            # time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
    else:
        if index ==3:
            print("Index 3")
            # time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
        if index ==4:
            # time.sleep(0.1)
            print("Index 4")
            ah.sendCommand("turn 1")
            time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
        if index == 2:
            print("Index 2")
            # time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
        if index == 3:
            print("Index 3")
            # time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
            ah.sendCommand("turn 1")
            time.sleep(0.1)
            ah.sendCommand("attack 1")
            time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
            ah.sendCommand("turn -1")
            time.sleep(0.1)
'''
Sample Observation:
{"DistanceTravelled":0,"TimeAlive":50,"MobsKilled":0,"PlayersKilled":0,"DamageTaken":0,"DamageDealt":0,
"Life":20.0,"Score":0,"Food":20,"XP":0,"IsAlive":true,"Air":300,"Name":"Enemy","XPos":5.5,"YPos":47.0,
"ZPos":5.5,"Pitch":50.0,"Yaw":180.0,"WorldTime":12000,"TotalTime":57}

'''


 

# movement(agent_host1, "south")
# movement(agent_host2, "north")
# movement(agent_host1, "south")
# movement(agent_host2, "north")
# movement(agent_host1, "east")
# movement(agent_host2, "west")
# attack(agent_host1, 1)
# attack(agent_host2, 3, enemy=True)
# attack(agent_host1, 2)
# attack(agent_host2, 4, enemy=True)
# attack(agent_host1, 3)
# attack(agent_host2, 1, enemy=True)
# attack(agent_host1, 4)
# attack(agent_host2, 2, enemy=True)
agent_score = 0
#count = 0
while true:
    #time.sleep(0.5)
    #count += 1
    #Scores should decrease with time and get a bonus if they win
    agent_score-=1
    agent_state = agent_host1.getWorldState()
    enemy_state = agent_host2.getWorldState()
    agent_ob = json.loads(agent_state.observations[-1].text)
    enemy_ob = json.loads(enemy_state.observations[-1].text)
    if agent_ob["Life"] == 0.0:
        print("Enemy Won!")
        agent_score-=100
        break
    if enemy_ob["Life"] == 0.0:
        print("Agent Won!")
        agent_score+=100
        break
    
    agent_position = (agent_ob["XPos"], agent_ob["ZPos"])
    enemy_position = (enemy_ob["XPos"], enemy_ob["ZPos"])
    
    agent_grid = agent_ob.get(u'floor3x3', 0)
    enemy_grid = enemy_ob.get(u'floor3x3', 0)
    
    agent_position = (agent_ob["XPos"], agent_ob["ZPos"])
    enemy_position = (enemy_ob["XPos"], enemy_ob["ZPos"])
    
    agent_grid = agent_ob.get(u'floor3x3', 0)
    enemy_grid = enemy_ob.get(u'floor3x3', 0)
    
    
    
    # movement(agent_host1, "south")
    # movement(agent_host2, "north")
    time.sleep(1)
    '''
    agentMoveString, agentBreakIndex = agentAlgo(agent_host1, agent_state, enemy_position, agent_grid)
    enemyMoveString, enemyBreakIndex = enemyAlgo(agent_host2, enemy_state, agent_position, enemy_grid)
    #Agent Turn to Break
    attack(agent_host1, agentBreakIndex)
    
    #Enemy Turn to Move
    movement(agent_host2, enemyMoveString)

    #Enemy Turn to Break
    attack(agent_host2, enemyBreakIndex)
    
    #Agent Turn to Move
    movement(agent_host1, agentMoveString)
    '''
# agent_sum = 0
# for reward in agent_state.rewards:
    # agent_sum += reward
# enemy_sum = 0
# for reward in agent_state.rewards:
    # enemy_sum += reward
# print("Agent Reward: {} \nEnemy Reward: {}".format(agent_sum, enemy_sum))


