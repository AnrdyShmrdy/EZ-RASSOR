#!/usr/bin/env python

import rospy
from sensor_msgs.msg import LaserScan
import numpy as np
from pointcloud_processor import PointCloudProcessor

class ObstacleDetector(PointCloudProcessor):
    def __init__(self, camera_height, min_hole_depth, min_obstacle_height,
                 scan_time, range_min, range_max):
        super(ObstacleDetector, self).__init__('obstacle_detection')

        self.scan_time = scan_time
        self.range_min = range_min
        self.range_max = range_max
        self.camera_height = camera_height
        self.min_hole_depth = min_hole_depth
        self.min_obstacle_height = min_obstacle_height
        self.threshold = 1.0

        self.cliffs_pub = rospy.Publisher('obstacle_detection/cliffs',
                                                LaserScan, queue_size = 10)
        self.positive_pub = rospy.Publisher('obstacle_detection/positive',
                                                LaserScan, queue_size = 10)
        self.combined_pub = rospy.Publisher('obstacle_detection/combined',
                                                LaserScan, queue_size = 10)

        rospy.loginfo("Obstacle Detection initialized.")

    def init_pc_info(self, camera_info):
        super(ObstacleDetector, self).init_pc_info(camera_info)

        # Get LaserScan-specific info from camera_info message
        self.ranges_size = camera_info.width
        self.frame_id = camera_info.header.frame_id
        self.angle_increment = (self.angle_max-self.angle_min)/(self.ranges_size-1)

    """Creates and returns a LaserScan object based on the given ranges list."""
    def create_laser_scan(self, ranges):
        scan = LaserScan()
        scan.header.stamp = rospy.Time.now()
        scan.header.frame_id = self.frame_id
        scan.angle_min = self.angle_min
        scan.angle_max = self.angle_max
        scan.angle_increment = self.angle_increment
        scan.time_increment = 0.0
        scan.scan_time = self.scan_time
        scan.range_min = self.range_min
        scan.range_max = self.range_max
        scan.ranges = ranges
        scan.intensities = []
        return scan

    def on_pc_update(self, pc):
        super(ObstacleDetector, self).on_pc_update(pc)
        self.point_cloud_to_laser_scan()

    """ Converts PointCloud2 to LaserScan

    Given a PointCloud2 message representing the area in front of the robot,
    this method uses the Farthest Point and Floor Projection methods
    proposed by Ghani et al. in "Detecting negative obstacle using Kinect
    sensor" to create LaserScans containing the farthest point the robot
    can see in each direction (to detect cliffs) and the closest holes
    to the robot in each direction. These LaserScans are combined with a
    LaserScan containing the closest above-ground obstacles in each
    direction to form a LaserScan that contains the closest cliff, hole,
    or above-ground obstacle in each direction.
    """
    def point_cloud_to_laser_scan(self):
        # Initial LaserScans assume infinite travel in every direction
        cliff_ranges = [float("nan")] * self.ranges_size
        positive_ranges = [float("nan")] * self.ranges_size
        min_ranges = [float("nan")] * self.ranges_size

        pc = self.get_points()

        if pc is not None:
            forward = pc[:,PointCloudProcessor.XYZ["FORWARD"]]
            right = pc[:,PointCloudProcessor.XYZ["RIGHT"]]
            down = pc[:,PointCloudProcessor.XYZ["DOWN"]]
            steps, dists = self.to_laser_scan_data(forward, right)

            # Create matrix where the steps, dists, and down arrays are the columns
            directions = np.column_stack((steps, dists, down))
            # Sort rows by the first column (steps); this is necessary for the next step
            directions = directions[directions[:,0].argsort()]
            # Group rows by step
            directions = np.split(directions, np.unique(directions[:,0], return_index=True)[1][1:],axis=0)

            # Loop through the rows for each step and find obstacles
            for direction in directions:
                # Sort rows for this step by the second column (dist)
                direction = direction[direction[:,1].argsort()]

                # Step is first column of any row
                step = int(direction[0, 0])

                # Since the rows are sorted by dist, the farthest point for this step is in the last row
                cliff_ranges[step] = direction[-1, 1]

                down1 = direction[:-1, 2]
                down2 = direction[1:, 2]

                dist1 = direction[:-1, 1]
                dist2 = direction[1:, 1]

                # Calculate slope for each pair of points
                slope = np.abs(np.divide(np.subtract(down2, down1), np.subtract(dist2, dist1)))

                # Find first index of row where the slope crosses the threshold
                condition = (slope > self.threshold)
                index = condition.argmax() if condition.any() else None

                if index is not None:
                    positive_ranges[step] = direction[index, 1]
                    min_ranges[step] = min(positive_ranges[step], cliff_ranges[step])
                else:
                    min_ranges[step] = cliff_ranges[step]

            self.cliffs_pub.publish(self.create_laser_scan(cliff_ranges))
            self.positive_pub.publish(self.create_laser_scan(positive_ranges))
            self.combined_pub.publish(self.create_laser_scan(min_ranges))

    def to_laser_scan_data(self, forward, right):
        # multiply angles by -1 to get counter-clockwise (right to left) ordering
        angles = np.negative(np.arctan2(right, forward))
        steps = np.divide(np.subtract(angles,self.angle_min),self.angle_increment).astype(int)
        # Find the distance each forward, right coordinate from the robot
        dists = np.sqrt(np.add(np.square(forward), np.square(right)))
        return steps, dists

"""Initializes obstacle detection."""
def obstacle_detection(camera_height_yaml=None, min_hole_depth_yaml=None, 
                       min_obstacle_height_yaml=None, scan_time=1./30, 
                       range_min=0.105, range_max=10.):
    od = ObstacleDetector(camera_height_yaml, min_hole_depth_yaml,
                          min_obstacle_height_yaml, scan_time, range_min,
                          range_max)

    rospy.spin()

if __name__ == "__main__":
    try:
        obstacle_detection()
    except:
        pass
