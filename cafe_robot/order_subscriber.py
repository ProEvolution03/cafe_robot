import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from std_msgs.msg import String
from nav2_msgs.action import NavigateToPose
import threading
import time


class OrderSubscriber(Node):
	"""
	OrderSubscriber Node — Robot Brain

	Listens for incoming cafe orders and executes multi-stop deliveries
	using Nav2's NavigateToPose action.

	Topics Subscribed:
		/order   — incoming order (format: "food_name:table1,table2,...")
		/cancel  — table cancellation (format: "table_number")
		/confirm — delivery confirmation at a location

	Topics Published:
		/awaiting_confirm — signals operator that robot needs confirmation
	"""

	TIMEOUT_SECONDS = 30

	LOCATIONS: dict = {
		'home':    (9.8957,   4.3635, 0.0),
		'kitchen': (7.7133,  -0.0996, 0.0),
		'table_1': (6.1936,   2.7551, 0.0),
		'table_2': (3.3841,  -1.9239, 0.0),
		'table_3': (-0.1936,  2.5368, 0.0),
	}

	def __init__(self):
		super().__init__('order_subscriber')

		self._cb_group = ReentrantCallbackGroup()

		# Subscriptions
		self.create_subscription(
			String, '/order', self._on_order, 10,
			callback_group=self._cb_group
		)
		self.create_subscription(
			String, '/cancel', self._on_cancel, 10,
			callback_group=self._cb_group
		)
		self.create_subscription(
			String, '/confirm', self._on_confirm, 10,
			callback_group=self._cb_group
		)

		# Publisher
		self.awaiting_pub = self.create_publisher(String, '/awaiting_confirm', 10)

		# Nav2 action client
		self._nav_client = ActionClient(
			self, NavigateToPose, 'navigate_to_pose',
			callback_group=self._cb_group
		)

		# State
		self._orders: list = []
		self._cancelled: set = set()
		self._confirmed: set = set()

		self._orders_lock    = threading.Lock()
		self._cancelled_lock = threading.Lock()
		self._confirmed_lock = threading.Lock()

		self._delivery_thread = None

		# Event to wake up confirmation wait loop instantly
		self._confirm_event = threading.Event()

		self.get_logger().info('✅ OrderSubscriber robot node started.')

		# Go to home on startup
		threading.Thread(target=self._startup, daemon=True).start()

	# ─── Startup ──────────────────────────────────────────────────────────────

	def _startup(self):
		self.get_logger().info('🏠 Moving to home position on startup...')
		self._navigate_to('home')
		self.get_logger().info('🏠 At home. Ready for orders.')

	# ─── Callbacks ────────────────────────────────────────────────────────────

	def _on_order(self, msg: String):
		raw = msg.data.strip()
		try:
			food, tables_raw = raw.split(':')
			tables = [f'table_{t.strip()}' for t in tables_raw.split(',')]
		except ValueError:
			self.get_logger().error(f'❌ Malformed order: "{raw}"')
			return

		self.get_logger().info(f'🍽️  Order received — {food} → {tables}')

		with self._orders_lock:
			self._orders.append((food, tables))
			if self._delivery_thread is None or not self._delivery_thread.is_alive():
				self._delivery_thread = threading.Thread(
					target=self._process_orders, daemon=True
				)
				self._delivery_thread.start()

	def _on_cancel(self, msg: String):
		table = f'table_{msg.data.strip()}'
		with self._cancelled_lock:
			self._cancelled.add(table)
		self._confirm_event.set()
		self.get_logger().info(f'🚫 Cancelled → {table}')

	def _on_confirm(self, msg: String):
		location = msg.data.strip()
		if location.isdigit():
			location = f'table_{location}'
		with self._confirmed_lock:
			self._confirmed.add(location)
		self._confirm_event.set()
		self.get_logger().info(f'✅ Confirmation received → {location}')

	# ─── Order Processing ─────────────────────────────────────────────────────

	def _process_orders(self):
		while True:
			with self._orders_lock:
				if not self._orders:
					break
				food, tables = self._orders.pop(0)
			
			with self._cancelled_lock: self._cancelled.clear()
			with self._confirmed_lock: self._confirmed.clear()

			self.get_logger().info(f'🚚 Processing — {food} to {tables}')

			# Step 1: Go to kitchen
			kitchen_ok = self._go_and_wait('kitchen')
			if not kitchen_ok:
				self.get_logger().warn('⚠️  Kitchen failed — going home.')
				self._navigate_to('home')
				continue

			# Step 2: Deliver to each table in sequence
			failed_tables = []
			for table in tables:
				with self._cancelled_lock:
					if table in self._cancelled:
						self.get_logger().info(f'⛔ {table} pre-cancelled — skipping.')
						continue

				success = self._go_and_wait(table)
				if not success:
					self.get_logger().warn(f'⚠️  {table} delivery failed.')
					failed_tables.append(table)

			# Step 3: Return to kitchen if any table failed
			if failed_tables:
				self.get_logger().info(f'🔁 Returning to kitchen for {failed_tables}.')
				self._navigate_to('kitchen')

			# Step 4: Go home
			self._navigate_to('home')
			self.get_logger().info('🏠 Delivery cycle complete.')

	# ─── Navigation + Confirmation ────────────────────────────────────────────

	def _go_and_wait(self, location: str) -> bool:
		reached = self._navigate_to(location)
		if not reached:
			return False
		if location == 'home':
			return True
		self.get_logger().info(f'⏳ At {location} — awaiting confirmation...')
		self.awaiting_pub.publish(String(data=location))
		return self._wait_for_confirmation(location)

	def _wait_for_confirmation(self, location: str) -> bool:
		deadline = time.time() + self.TIMEOUT_SECONDS
		while time.time() < deadline:
			remaining = deadline - time.time()
			self._confirm_event.wait(timeout=min(remaining, 1.0))
			self._confirm_event.clear()

			with self._cancelled_lock:
				if location in self._cancelled:
					self.get_logger().warn(f'⛔ {location} cancelled.')
					return False

			with self._confirmed_lock:
				if location in self._confirmed:
					self._confirmed.discard(location)
					self.get_logger().info(f'✅ Confirmed at {location}.')
					return True

		self.get_logger().warn(f'⏰ Timeout at {location}.')
		return False

	# ─── Navigation ───────────────────────────────────────────────────────────

	def _navigate_to(self, location: str) -> bool:
		if location not in self.LOCATIONS:
			self.get_logger().error(f'❌ Unknown location: "{location}"')
			return False

		x, y, w = self.LOCATIONS[location]

		goal = NavigateToPose.Goal()
		goal.pose.header.frame_id = 'map'
		goal.pose.header.stamp = self.get_clock().now().to_msg()
		goal.pose.pose.position.x = x
		goal.pose.pose.position.y = y
		goal.pose.pose.orientation.w = w

		self.get_logger().info(f'📍 Navigating to {location} ({x}, {y})...')
		self._nav_client.wait_for_server()

		# Send goal using callbacks instead of spin_once
		goal_done = threading.Event()
		goal_handle_container = [None]

		def on_goal_response(future):
			goal_handle_container[0] = future.result()
			goal_done.set()

		self._nav_client.send_goal_async(
			goal,
			feedback_callback=lambda fb: None
		).add_done_callback(on_goal_response)

		goal_done.wait()
		goal_handle = goal_handle_container[0]

		if not goal_handle or not goal_handle.accepted:
			self.get_logger().error(f'❌ Goal to {location} rejected.')
			return False

		self.get_logger().info(f'🎯 Moving to {location}...')

		result_done = threading.Event()
		result_container = [None]

		def on_result(future):
			result_container[0] = future.result()
			result_done.set()

		goal_handle.get_result_async().add_done_callback(on_result)

		# Poll for result while checking for mid-navigation cancellations
		while not result_done.wait(timeout=0.2):
			with self._cancelled_lock:
				if location in self._cancelled:
					self.get_logger().warn(f'⛔ Cancelling goal to {location}.')
					cancel_done = threading.Event()
					goal_handle.cancel_goal_async().add_done_callback(
						lambda f: cancel_done.set()
					)
					cancel_done.wait()
					return False

		result = result_container[0]
		if result:
			self.get_logger().info(f'✅ Reached {location}.')
			return True
		else:
			self.get_logger().warn(f'⚠️  Failed to reach {location}.')
			return False


def main(args=None):
	rclpy.init(args=args)
	node = OrderSubscriber()
	executor = MultiThreadedExecutor()
	executor.add_node(node)
	try:
		executor.spin()
	except KeyboardInterrupt:
		node.get_logger().info('🔌 OrderSubscriber shutting down.')
	finally:
		node.destroy_node()
		rclpy.shutdown()


if __name__ == '__main__':
	main()
