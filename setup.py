from setuptools import setup
import os
from glob import glob

package_name = 'cafe_robot'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name, glob('*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='aakash_sivakumar',
    maintainer_email='aakashiyer03@gmail.com',
    description='Cafe Robot Delivery — ROS2 Humble delivery system.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'order_robot      = cafe_robot.order_robot:main',
            'order_subscriber = cafe_robot.order_subscriber:main',
        ],
    },
)
