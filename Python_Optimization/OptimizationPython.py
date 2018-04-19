#!/usr/bin/env python
"""Calibration Optimization Camera-Camera

Program whose function is to optimize the calibration of n cameras at the same time.
"""

#-------------------------------------------------------------------------------
#--- IMPORT MODULES
#-------------------------------------------------------------------------------
import time  # Estimate time of process
import argparse  # Read command line arguments
import numpy as np  # Arrays and opencv images
import cv2  # OpenCV library
import glob  # Finds all the pathnames
import sys
import os  # Using operating system dependent functionality
from tqdm import tqdm  # Show a smart progress meter
import matplotlib.pyplot as plt  # Library to do plots 2D
import matplotlib.animation as animation  # Animate plots
from matplotlib import gridspec  # Make subplott
from mpl_toolkits.mplot3d import Axes3D  # Library to do plots 3D
from scipy.sparse import lil_matrix  # Lib Sparse bundle adjustment
from scipy.optimize import least_squares  # Lib optimization
import cv2.aruco as aruco  # Aruco Markers
import pickle
import networkx as nx

#-------------------------------------------------------------------------------
#--- DEFINITIONS
#-------------------------------------------------------------------------------


class stru:
    def __init__(self):
        self.filename = None
        self.raw = None
        self.gray = None
        self.corners = None
        self.rvec = None
        self.tvec = None
        self.xypix = None


class cam:
    def __init__(self):
        self.dxyz = None
        self.rod = None
        self.calibrated = False


class mark:
    def __init__(self):
        self.id = None
        self.xyz = None
        self.T = None
        self.calibrated = False


#-------------------------------------------------------------------------------
#--- HEADER
#-------------------------------------------------------------------------------
__author__ = "Filipe Oliveira Costa"
__date__ = "Abril 2018"
__copyright__ = "Copyright 2015, V3V"
__credits__ = ["Filipe Oliveira Costa"]
__license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Filipe Costa"
__email__ = "costa.filipe@ua.pt"
__status__ = "Development"

#-------------------------------------------------------------------------------
#--- FUNCTION DEFINITION
#-------------------------------------------------------------------------------


def getWorldPoints(s, square_size):
    """Get Global coordinates

    """
    n_points = len(s[0].corners)

    nx = 8  # number squares to direction x
    ny = 6  # number squares to direction y
    worldPoints = np.zeros((n_points, 4))

    for iy in range(ny):
        y = iy * square_size
        for ix in range(nx):
            x = ix * square_size
            worldPoints[ix+nx*iy, 0] = x
            worldPoints[ix+nx*iy, 1] = y
            worldPoints[ix+nx*iy, 2] = 0
            worldPoints[ix+nx*iy, 3] = 1

    worldPoints = worldPoints.transpose()
    return worldPoints


def TFromDxyzDCM(dxyz, rod):
    """Transformation matrix

        Homogeneous transformation matrix from dxyz and rod
    """
    T = np.zeros((4, 4))
    T[3, 3] = 1
    T[0:3, 3] = dxyz.transpose()
    DCM = cv2.Rodrigues(rod)
    T[0:3, 0:3] = DCM[0]

    return T


def DxyzDCMFromT(T):
    """Transformation matrix

        Homogeneous transformation matrix from DCM
    """
    dxyz = T[0:3, 3]
    dxyz = dxyz.transpose()
    rod = cv2.Rodrigues(T[0:3, 0:3])

    return dxyz, rod


def points2image(dxyz, rod, K, P, dist):
    """Converts world points into image points

        Computes the list of pixels given by the projection of P 3D points onto the image given the postion and intrinsics of the camera
    """
    # Compute T matrix from dxyz and rod
    T = TFromDxyzDCM(dxyz, rod)

    # Calculation of the point in the image in relation to the chess reference
    xypix = []

    fx = K[0, 0]
    fy = K[1, 1]
    cx = K[0, 2]
    cy = K[1, 2]

    k1 = dist[0, 0]
    k2 = dist[0, 1]
    p1 = dist[0, 2]
    p2 = dist[0, 3]
    k3 = dist[0, 4]

    P = P.transpose()[:, 0:3]

    for p in P:

        rot = np.matrix(T[0: 3, 0: 3])
        xyz = rot.dot(p) + T[0: 3, 3]

        xl = xyz[0, 0] / xyz[0, 2]
        yl = xyz[0, 1] / xyz[0, 2]

        r_square = xl**2 + yl**2

        xll = xl * (1 + k1 * r_square + k2 * r_square**2 + k3 *
                    r_square**3) + 2 * p1 * xl * yl + p2 * (r_square + 2 * xl**2)
        yll = yl * (1 + k1 * r_square + k2 * r_square**2 + k3 *
                    r_square**3) + p1 * (r_square + 2 * yl**2) + 2 * p2 * xl * yl

        u = fx * xll + cx
        v = fy * yll + cy

        xypix.append([u, v])

    return np.array(xypix)


def costFunction(x0, worldPoints, dist, s, intrinsics):
    """Cost function
    """
    # Geometric transformation
    for k in range(K):

        dxyz = x0[k*N: k*N+3]
        rod = x0[k*N+3: k*N+6]

        s[k].xypix = points2image(
            dxyz, rod, intrinsics, worldPoints, dist)

        ### Draw iterate projections ###

    # Cost calculation
    sum_dist = 0

    for ni in range(K):

        sum_dist = sum_dist + sum((s[ni].corners[:, 0][..., 0] - s[ni].xypix[:, 0])
                                  ** 2 + (s[ni].corners[:, 0][..., 1] - s[ni].xypix[:, 1])**2)

    fc = sum_dist ** (1/2.0)
    cost = fc

    return cost


# def objectiveFunction(x):
#     """Compute the error between the several aruco marker positions

#         This funcion uses the total reprojection error

#     """
#     residuals = 0

#     return residuals



#-------------------------------------------------------------------------------
#--- MAIN
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    #---------------------------------------
    #--- Argument parser
    #---------------------------------------
    # ap = argparse.ArgumentParser()
    # ap.add_argument("-y", "--calibration_yaml",
    # help="path to the yaml camera calibration file", required=True)
    # args = vars(ap.parse_args())

    #---------------------------------------
    #--- Intitialization
    #---------------------------------------

    # Read all images (each image correspond to a camera)
    images = glob.glob((os.path.join('../CameraImages', '*.png')))
    K = len(images)

    # Start the graph and insert nodes (the images)
    G = nx.Graph()
    for i in range(K):
        node_name = "camera " + str(i+1)
        G.add_node(node_name)
    list_nodes = list(G.node)
    # print list_nodes[0]
    # exit()

    # Read data calibration camera
    # (Dictionary elements -> "mtx", "dist")
    d = np.load("cameraParameters.npy")

    # Define aruco
    aruco_dict = aruco.Dictionary_get(aruco.DICT_ARUCO_ORIGINAL)
    parameters = aruco.DetectorParameters_create()
    marksize = 0.082

    # Intrinsic matrix
    mtx = d.item().get('mtx')
    intrinsics = np.zeros((3, 4))
    intrinsics[:, :3] = mtx
    intrinsics[:, 3] = np.array([0, 0, 0]).transpose()  # homogenize

    dist = d.item().get('dist')

    s = [stru() for i in range(K)]

    for i in range(K):
        s[i].filename = images[i]

    fig = plt.figure()
    gs = gridspec.GridSpec(K, K+1)

    for k in tqdm(range(K)):

        # load image
        s[k].raw = cv2.imread(s[k].filename)
        s[k].gray = cv2.cvtColor(s[k].raw, cv2.COLOR_BGR2GRAY)

        # lists of ids and the corners beloning to each id
        s[k].corners, s[k].ids, rejectedImgPoints = aruco.detectMarkers(
            s[k].gray, aruco_dict, parameters=parameters)

        font = cv2.FONT_HERSHEY_SIMPLEX  # font for displaying text

        nids = len(s[k].ids)
        if np.all(nids != 0):
            s[k].rvec, s[k].tvec, _ = aruco.estimatePoseSingleMarkers(
                s[k].corners, marksize, mtx, dist)  # Estimate pose of each marker
            for i in range(nids):
                aruco.drawAxis(s[k].raw, mtx, dist, s[k].rvec[i],
                               s[k].tvec[i], 0.05)  # Draw Axis

                cv2.putText(s[k].raw, "Id: " + str(s[k].ids[i][0]), (s[k].corners[i][0][0][0], s[k].corners[i][0][0][1]),
                            font, 1, (0, 255, 100), 2, cv2.LINE_AA)

            s[k].raw = aruco.drawDetectedMarkers(s[k].raw, s[k].corners)

        # drawing sttuff
        ax = fig.add_subplot(gs[k, K])

        ax.imshow(cv2.cvtColor(s[k].raw, cv2.COLOR_BGR2RGB))
        ax.axis('off')

    #---------------------------------------
    #--- Initial guess for parameters (create x0).
    #---------------------------------------

    # Find ids of aruco markers existents
    list_of_ids = []
    for i in tqdm(range(K)):
        a = np.array(list_of_ids)
        b = s[i].ids
        c = [e for e in b if e not in a]
        if len(c) > 0:
            list_of_ids = np.append(list_of_ids, c)

    cam = [cam() for i in range(K)]

    marks = [mark() for i in range(len(list_of_ids))]
    for i in tqdm(range(len(marks))):
        marks[i].id = list_of_ids[i]

    # Define global reference marker
    marks[0].xyz = np.array([[-marksize/2, marksize/2, 0],
                             [marksize/2, marksize/2, 0],
                             [marksize/2, -marksize/2, 0],
                             [-marksize/2, -marksize/2, 0]])

    marks[0].T = np.eye(4)
    marks[0].calibrated = True

    loop = 0
    while loop != K+len(marks):
        loop = 0
        for i in tqdm(range(K)):
            if not cam[i].calibrated:
                for u in range(len(s[i].ids)):
                    for j in range(len(marks)):
                        if s[i].ids[u] == marks[j].id:
                            if marks[j].calibrated and not cam[i].calibrated:
                                cam[i].dxyz = s[i].tvec[u]
                                cam[i].rod = s[i].rvec[u]
                                cam[i].calibrated = True
                                for uu in range(len(s[i].ids)):
                                    for jj in range(len(marks)):
                                        if s[i].ids[uu] == marks[jj].id:
                                            if not marks[jj].calibrated:
                                                Tcam = TFromDxyzDCM(
                                                    cam[i].dxyz[0], cam[i].rod[0])
                                                Tmark = TFromDxyzDCM(
                                                    s[i].tvec[uu][0], s[i].rvec[uu][0])
                                                marks[jj].T = Tcam * Tmark

                                                rot = np.matrix(
                                                    marks[jj].T[0: 3, 0: 3])
                                                marks[jj].xyz = np.zeros(
                                                    (4, 3))
                                                for x in range(4):
                                                    p = marks[0].xyz[x]
                                                    marks[jj].xyz[x] = rot.dot(
                                                        p) + marks[jj].T[0: 3, 3]
                                                    marks[jj].calibrated = True
        for ll in range(K):
            if cam[ll].calibrated:
                loop = loop + 1
        for ll in range(len(marks)):
            if marks[ll].calibrated:
                loop = loop + 1

    for i in range(K):
        print cam[i].dxyz

    for i in range(len(marks)):
        print marks[i].xyz

    exit()
    # Compute Chessboard 3D worl Coordinates
    worldPoints = getWorldPoints(s, 0.105)

    # Draw 3d plot with reference systems
    ax3D = fig.add_subplot(gs[:, :K], projection='3d')
    ax3D.scatter(worldPoints[0, :], worldPoints[1, :],
                 worldPoints[2, :], c='b', marker='*')
    ax3D.scatter(worldPoints[0, 0], worldPoints[1, 0],
                 worldPoints[2, 0], c='g', marker='o')

    # Referential
    exsize = 0.150
    ax3D.plot([0, exsize], [0, 0], [0, 0], 'r-')
    ax3D.plot([0, 0], [0, exsize], [0, 0], 'g-')
    ax3D.plot([0, 0], [0, 0], [0, exsize], 'b-')

    ax3D.set_xlabel('x axis')
    ax3D.set_ylabel('y axis')
    ax3D.set_zlabel('z axis')

    ################
    x0 = []  # the parameters(extend list x0 as needed)

    # # ---- Camera 1 - Position and Rotation
    # dxyz = [, , ]
    # rod = [, , ]

    # x0 = x0 + dxyz + rod

    # # ---- Camera 2 - Position and Rotation
    # dxyz = [, , ]
    # rod = [, , ]

    # x0 = x0 + dxyz + rod

    # # ---- Camera 3 - Position and Rotation
    # dxyz = [, , ]
    # rod = [, , ]

    # x0 = x0 + dxyz + rod

    # convert list to array
    x0 = np.array(x0)

    # print x0
    print("number of parameters = " + str(len(x0)))

    # Draw initial estimate
    N = 6  # num_values_per_camera
    for k in tqdm(range(K)):
        dxyz = x0[k*N: k*N+3]
        rod = x0[k*N+3: k*N+6]

        s[k].xypix = points2image(
            dxyz, rod, intrinsics, worldPoints, dist)

        # Draw intial projections
        ax = fig.add_subplot(gs[k, K])
        plt.plot(s[k].xypix[:, 0], s[k].xypix[:, 1], 'r*')
        plt.plot(s[k].xypix[0, 0], s[k].xypix[0, 1], 'g*')

    #---------------------------------------
    #--- Test call of objective function
    #---------------------------------------
    # call objective function with initial guess (just for testing)

    # initial_residuals = objectiveFunction(x0)
    # print("initial_residuals = " + str(initial_residuals))

    #---------------------------------------
    #--- Set the bounds for the parameters
    #---------------------------------------
    # bounds : 2-tuple of array_like, optional
    # Lower and upper bounds on independent variables. Defaults to no bounds. Each array must match the size of x0 or be a scalar, in the latter case a bound will be the same for all variables. Use np.inf with an appropriate sign to disable bounds on all or some variables.
    # camera_params = params[:n_cameras * 9].reshape((n_cameras, 9))
    # points_3d = params[n_cameras * 9:].reshape((n_points, 3))

    # Bmin = []
    # Bmax = []
    # for i in range(0, len(views)):
    #     for i in range(0, 6):
    #         Bmin.append(-np.inf)
    #         Bmax.append(np.inf)

    # delta = 0.1
    # for i in range(len(views) * 6, len(x0)):
    #     Bmin.append(x0[i] - delta)
    #     Bmax.append(x0[i] + delta)

    # # for i in range(len(x0)-4, len(x0)):
    #     # Bmin.append(-np.inf)
    #     # Bmax.append(np.inf)

    # bounds = (Bmin, Bmax)

    #---------------------------------------
    #--- Optimization (minimization)
    #---------------------------------------
    print("\n\nStarting minimization")

    # --- Without sparsity matrix
    t0 = time.time()

    res = least_squares(costFunction, x0, verbose=2, x_scale='jac',
                        ftol=1e-10, xtol=1e-10, method='trf', args=(worldPoints, dist, s, intrinsics))
    # bounds=bounds
    t1 = time.time()

    print("Optimization took {0:.0f} seconds".format(t1 - t0))

    for k in tqdm(range(K)):
        ax = fig.add_subplot(gs[k, K])
        plt.plot(s[k].xypix[:, 0], s[k].xypix[:, 1], 'y*')
        plt.plot(s[k].xypix[0, 0], s[k].xypix[0, 1], 'g*')

    plt.show()

    #---------------------------------------
    #--- Present the results
    #---------------------------------------

    # solution_residuals = objectiveFunction(
    # res.x, marker_detections, views, pinhole_camera_model)

    # print("OPTIMIZATON FINISHED")
    # print("Initial (x0) average error = " + str(np.average(initial_residuals)))
    # print("Solution average error = " + str(np.average(solution_residuals)))
