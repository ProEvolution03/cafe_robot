# Café Robot Delivery — Technical Documentation

**Tech Stack:** ROS2 Humble | TurtleBot3 Waffle | Nav2 | Cartographer SLAM  

---

## 1. Overview

The Café Delivery Robot system is an autonomous delivery system for a Cafe environment. It picks up food from the kitchen and delivers it to customer tables, handling timeouts, cancellations, and multi-table orders.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ROS2 Node Graph                      │
│                                                         │
│  [order_robot]──┐────/order──────────────────────┐      │
│                 │                                ▼      │
│                 │────/confirm────────────────────┐      │  
│                 │                                ▼      │ 
│                 │────/cancel─────────────────────┐      │
│                                                  ▼      │
│                                    [order_subscriber]   │      
│                                                  │      │
│        ────────────────/awaiting_confirm◄────────┘      │
│        │                                                │
│        ▼                                                │
│  [order_robot] ──NavigateToPose──►   [Nav2 Stack]       │
│                                           │             │
│                                     [Cartographer]      │
│                                           │             │
│                                   [TurtleBot3 Waffle]   │
└─────────────────────────────────────────────────────────┘
```

### Nodes

| Node | Role |
|------|------|
| `order_subscriber` | Core state machine, Nav2 goals, timeout logic |
| `order_robot` | CLI interface to send orders and confirmations |

### Topics

| Topic | Type | Direction | Purpose |
|-------|------|-----------|---------|
| `/order` | `std_msgs/String` | → robot | Comma-separated table names |
| `/confirm` | `std_msgs/String` | → robot | `"kitchen"` or `"table1"` etc. |
| `/cancel` | `std_msgs/String` | → robot | Table name to cancel |
| `/awaiting_confirm` | `std_msgs/String` | robot → | The waiting topic that reaches destination and signals to subscriber for confirmation |

---

## 3. State Machine

```
            ┌─────────────────────────────┐
            │           IDLE              │◄──────────────────┐
            └────────────┬────────────────┘                   │
                         │ /order received                     │
                         ▼                                     │
            ┌─────────────────────────────┐                   │
            │      GOING_TO_KITCHEN       │                   │
            └────────────┬────────────────┘                   │
                         │ arrived                             │
                         ▼                                     │
            ┌─────────────────────────────┐                   │
            │      WAITING_KITCHEN        │──timeout──► go home
            └────────────┬────────────────┘                   │
                         │ confirmed                           │
                         ▼                                     │
            ┌─────────────────────────────┐                   │
            │       GOING_TO_TABLE        │◄──────────────┐   │
            └────────────┬────────────────┘               │   │
                         │ arrived                         │   │
                         ▼                                 │   │
            ┌─────────────────────────────┐               │   │
            │       WAITING_TABLE         │──timeout──►(skip/kitchen)
            └────────────┬────────────────┘               │   │
                         │ confirmed                       │   │
                         │ more tables? ──────────────────┘   │
                         │ no more tables                      │
                         ▼                                     │
            ┌─────────────────────────────┐                   │
            │         GOING_HOME          │───────────────────┘
            └─────────────────────────────┘
```

---

## 4. Package Structure

```
cafe_robot/
├── cafe_robot/
│   ├── __init__.py
│   ├── order_robot.py        ← The node that publishes the input from controller
│   └── order_subscriber.py   ← Node that subscribes to the topics /order, /confirm or /cancel
├── hotel_map.pgm             ← Café occupancy grid
├── hotel_map.yaml            ← Map metadata
├── cafe_world.launch.py      ← Launch file for the world of the cafe.
├── french_door_cafe.world    ← World file for the cafe environment.
├── package.xml
├── setup.py
└── setup.cfg
```

---

## 5. Map & Waypoints

### Layout

```
┌──────────────────────────────────────────┐
│  [KITCHEN]  │         Dining Area        │
│      ★      │                            │
│             │            [T2]★           │
│             │                            │
│                                          │
│                   [T1]★        [T3]★     │
│                                          │
│ ★ HOME Position                          │
└──────────────────────────────────────────┘
```

### Waypoint Coordinates (world frame)

| Location |  X (m) | Y (m)  | Yaw (rad) |
|----------|--------|--------|-----------|
| home     | 9.8957 | 4.3635 | 0.0 |
| kitchen  | 7.7133 |-0.0996 | 0.0 |
| table1   | 6.1936 | 2.7551 | 0.0 |
| table2   | 3.3841 |-1.9239 | 0.0 |
| table3   |-0.1936 | 2.5368 | 0.0 |

---

## 6. Build & Run

### Prerequisites

```bash
# Install ROS2 Humble + TurtleBot3 packages
sudo apt install ros-humble-turtlebot3*
sudo apt install ros-humble-nav2-bringup
sudo apt install ros-humble-cartographer-ros
export TURTLEBOT3_MODEL=waffle
```

### Build

```bash
cd ~/ros2_ws/src
git clone ""
cd ~/ros2_ws
colcon build --packages-select cafe_robot
source install/setup.bash
```

### Mapping

# Mapping entirely done in the following steps :

```bash
# In Terminal 1
ros2 launch cafe_robot cafe_world.launch.py


# In Terminal 2
ros2 launch turtlebot3_cartographer cartographer.launch.py use_sim_time:=True
```

The mapping can be done in 2 ways :

```bash
#1. 2D Pose estimate in RViz2 - Just leading the robot in certain directions for mapping.

#2. Teleop Keyboard in a 3rd Terminal - Use the Teleop keyboard to manually move the robot around for mapping.
ros2 run turtlebot3_teleop teleop_keyboard
```
Save the map in the workspace directory and get its path. 

# NOTE : Map already created, saved and uploaded in the repository.

### Run Nodes Individually

# I. Open the Gazebo world again

```bash
# In Terminal 1

cd ~/ros2_ws
colcon build --packages-select cafe_robot
source install/setup.bash
ros2 launch cafe_robot cafe_world.launch.py
```

# II. Running RViz2 using the map obtained

```bash
# In Terminal 2

cd ~/ros2_ws
colcon build --packages-select cafe_robot
source install/setup.bash
ros2 launch turtlebot3_navigation2 navigation2.launch.py   use_sim_time:=True   map:=$YOUR_PATH/cafe_map.yaml
```

# III. Run the nodes separately, the order_robot and order_subscriber nodes in separate terminals.

```bash
# In Terminal 3

cd ~/ros2_ws
colcon build --packages-select cafe_robot
source install/setup.bash
ros2 run cafe_robot order_robot
```
```bash
cd ~/ros2_ws
colcon build --packages-select cafe_robot
source install/setup.bash
ros2 run cafe_robot order_subscriber
```

---

