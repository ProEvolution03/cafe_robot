import rclpy
import rclpy.executors
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from std_msgs.msg import String
import threading
import time


class OrderRobot(Node):
	"""
	OrderRobot Node — Operator Interface

	Human-facing terminal for the French Door Cafe butler system.
	Publishes orders, cancellations, and confirmations to the robot.
	Listens for awaiting_confirm signals and handles automatic timeouts.

	Topics Published:
		/order   — new food order (format: "food_name:table1,table2,...")
		/cancel  — cancel a table's order (format: "table_number")
		/confirm — confirm robot arrival at a location

	Topics Subscribed:
		/awaiting_confirm — robot signals it is waiting at a location
	"""

	TIMEOUT_SECONDS = 30

	def __init__(self):
		super().__init__('order_robot')

		self._cb_group = ReentrantCallbackGroup()

		# Publishers
		self.order_pub   = self.create_publisher(String, '/order',   10)
		self.cancel_pub  = self.create_publisher(String, '/cancel',  10)
		self.confirm_pub = self.create_publisher(String, '/confirm', 10)

		# Subscriber
		self.create_subscription(
			String, '/awaiting_confirm',
			self._on_awaiting_confirm, 10,
			callback_group=self._cb_group
		)

		self._pending: dict = {}
		self._lock = threading.Lock()

		threading.Thread(target=self._input_loop,   daemon=True).start()
		threading.Thread(target=self._timeout_loop, daemon=True).start()

		self.get_logger().info('✅ OrderRobot operator node started.')

	# ─── Subscription Callback ────────────────────────────────────────────────

	def _on_awaiting_confirm(self, msg: String):
		location = msg.data.strip()
		with self._lock:
			self._pending[location] = time.time()
		print(f'\n{"="*50}')
		print(f'🔔  ROBOT WAITING AT: {location.upper()}')
		print(f'{"="*50}')
		print(f'   → Type "confirm" then press Enter')
		print(f'   → Then type "{location}" and press Enter')
		print(f'{"="*50}\n')
		print('Command: ', end='', flush=True)

	# ─── Input Loop ───────────────────────────────────────────────────────────

	def _input_loop(self):
		while rclpy.ok():
			print('\n┌─────────────────────────────┐')
			print('│   French Door Cafe — Robot  │')
			print('├─────────────────────────────┤')
			print('│  order   → Place new order  │')
			print('│  cancel  → Cancel a table   │')
			print('│  confirm → Confirm delivery │')
			print('└─────────────────────────────┘')

			cmd = input('Command: ').strip().lower()

			if cmd == 'order':
				self._handle_order()
			elif cmd == 'cancel':
				self._handle_cancel()
			elif cmd == 'confirm':
				self._handle_confirm()
			else:
				print('❌ Unknown command. Try: order / cancel / confirm')

	def _handle_order(self):
		food   = input('Food item: ').strip()
		tables = input('Table number(s) — comma separated (e.g. 1 or 1,2,3): ').strip()
		if not food or not tables:
			print('❌ Food item and table number(s) are required.')
			return
		payload = f'{food}:{tables}'
		self.order_pub.publish(String(data=payload))
		self.get_logger().info(f'📦 Order published → {payload}')

	def _handle_cancel(self):
		table = input('Table number to cancel: ').strip()
		if not table.isdigit():
			print('❌ Please enter a valid table number.')
			return
		self.cancel_pub.publish(String(data=table))
		self.get_logger().info(f'🚫 Cancel published → table_{table}')

	def _handle_confirm(self):
		with self._lock:
			if not self._pending:
				print('❌ No locations currently awaiting confirmation.')
				return
			waiting = list(self._pending.keys())

		print(f'Awaiting confirmation at: {", ".join(waiting)}')
		print('(Press Enter to confirm the first one, or type the location)')
		location = input('Confirm location: ').strip()

		if not location and waiting:
			location = waiting[0]

		with self._lock:
			if location in self._pending:
				self.confirm_pub.publish(String(data=location))
				self.get_logger().info(f'✅ Confirmed → {location}')
				del self._pending[location]
			else:
				print(f'❌ "{location}" is not awaiting confirmation.')
				print(f'    Try one of: {", ".join(waiting)}')

	# ─── Timeout Loop ─────────────────────────────────────────────────────────

	def _timeout_loop(self):
		while rclpy.ok():
			time.sleep(1)
			now = time.time()
			expired = []

			with self._lock:
				for location, timestamp in list(self._pending.items()):
					if now - timestamp > self.TIMEOUT_SECONDS:
						expired.append(location)

			for location in expired:
				# ONLY cancel/confirm if the robot is actually still waiting there
				self.get_logger().warn(f'⏰ Timeout at {location}.')
				
				if location.startswith('table_'):
					table_num = location.split('_')[1]
					self.cancel_pub.publish(String(data=table_num))
				else:
					# If it's the kitchen, just confirm so it can move on
					self.confirm_pub.publish(String(data=location))
				
				with self._lock:
					# CRITICAL: Clear ALL pending timeouts once one expires 
					# to prevent "ghost" cancellations for the rest of the trip
					self._pending.clear() 
					break


def main(args=None):
	rclpy.init(args=args)
	node = OrderRobot()
	executor = rclpy.executors.MultiThreadedExecutor()
	executor.add_node(node)
	try:
		executor.spin()
	except KeyboardInterrupt:
		node.get_logger().info('🔌 OrderRobot shutting down.')
	finally:
		node.destroy_node()
		rclpy.shutdown()


if __name__ == '__main__':
	main()
